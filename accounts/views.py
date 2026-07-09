import csv
import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, DecimalField, FloatField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from .forms import (
	AccountProfileForm,
	ProfilePhotoForm,
)
from .models import AccountProfile, ActivityLog, LoginAttemptLog, LoginIPBlock, LoginSecurity, SuspiciousActivity
from .permissions import user_has_custom_permission
from courses.models import Course, Enrollment, HomeworkSubmission
from exams.models import Exam, StudentExam
from notifications.models import Notification
from payments.models import Payment
from students.models import Student
from subscriptions.models import StudentSubscription
from teachers.models import Teacher


GROUP_ADMINISTRATOR = "Administrator"
GROUP_TEACHER = "Teacher"
GROUP_STUDENT = "Student"
GROUP_PARENT = "Parent"

DASHBOARD_SHARED_STATS_CACHE_KEY = "accounts:dashboard:shared_stats:v1"
DASHBOARD_SHARED_STATS_CACHE_TIMEOUT = 60
MAX_FAILED_LOGIN_ATTEMPTS = 6

GENERIC_AUTH_ERROR_MESSAGE = "بيانات الدخول غير صحيحة"
ROLE_CONFIG = {
	"administrator": {
		"template": "admin-login.html",
		"group": GROUP_ADMINISTRATOR,
		"redirect_name": "admin_dashboard",
		"required_permission": "accounts.view_accountprofile",
		"required_custom_permission": "access.portal.administrator",
	},
	"teacher": {
		"template": "teacher-login.html",
		"group": GROUP_TEACHER,
		"redirect_name": "teacher_dashboard",
		"required_permission": "teachers.view_teacher",
		"required_custom_permission": "access.portal.teacher",
	},
	"student": {
		"template": "student-login.html",
		"group": GROUP_STUDENT,
		"redirect_name": "student_dashboard",
		"required_permission": "students.view_student",
		"required_custom_permission": "access.portal.student",
	},
	"parent": {
		"template": "parent-login.html",
		"group": GROUP_PARENT,
		"redirect_name": "parent_dashboard",
		"required_permission": None,
		"required_custom_permission": "access.portal.parent",
	},
}


def _user_has_role_access(user, role_key):
	config = ROLE_CONFIG[role_key]
	in_group = user.is_superuser or user.groups.filter(name=config["group"]).exists()
	required_permission = config.get("required_permission")
	has_permission = user.is_superuser or not required_permission or user.has_perm(required_permission)

	required_custom_permission = config.get("required_custom_permission")
	has_custom_permission = user_has_custom_permission(user, required_custom_permission)

	return in_group and has_permission and has_custom_permission


def _get_dashboard_shared_stats():
	shared_stats = cache.get(DASHBOARD_SHARED_STATS_CACHE_KEY)
	if shared_stats is not None:
		return shared_stats

	teacher_stats = Teacher.objects.aggregate(
		total=Count("id"),
		active=Count("id", filter=Q(status=Teacher.Status.ACTIVE)),
	)
	payment_stats = Payment.objects.filter(status=Payment.Status.SUCCESSFUL).aggregate(
		total_revenue=Coalesce(
			Sum("amount"),
			Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
		)
	)

	shared_stats = {
		"total_students": Student.objects.count(),
		"total_teachers": teacher_stats["total"],
		"active_teachers": teacher_stats["active"],
		"total_revenue": payment_stats["total_revenue"],
		"published_courses": Course.objects.filter(status=Course.Status.PUBLISHED).count(),
		"active_subscriptions": StudentSubscription.objects.filter(
			status=StudentSubscription.Status.ACTIVE
		).count(),
	}
	cache.set(DASHBOARD_SHARED_STATS_CACHE_KEY, shared_stats, DASHBOARD_SHARED_STATS_CACHE_TIMEOUT)
	return shared_stats


def _render_role_template(request, role_key, *, status=200):
	return render(request, ROLE_CONFIG[role_key]["template"], status=status)


def _get_client_ip(request):
	forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
	if forwarded_for:
		return forwarded_for.split(",")[0].strip()
	return request.META.get("REMOTE_ADDR")


def _extract_browser_and_os(user_agent):
	agent = (user_agent or "")[:512]
	browser = "Unknown"
	operating_system = "Unknown"

	browser_patterns = [
		(r"Edg/", "Edge"),
		(r"OPR/|Opera", "Opera"),
		(r"Chrome/", "Chrome"),
		(r"Firefox/", "Firefox"),
		(r"Safari/", "Safari"),
		(r"MSIE|Trident/", "Internet Explorer"),
	]
	os_patterns = [
		(r"Windows NT", "Windows"),
		(r"Android", "Android"),
		(r"iPhone|iPad|iOS", "iOS"),
		(r"Mac OS X|Macintosh", "macOS"),
		(r"Linux", "Linux"),
	]

	for pattern, name in browser_patterns:
		if re.search(pattern, agent, flags=re.IGNORECASE):
			browser = name
			break

	for pattern, name in os_patterns:
		if re.search(pattern, agent, flags=re.IGNORECASE):
			operating_system = name
			break

	return browser[:128], operating_system[:128]


def _is_ip_rate_limited(request, role_key):
	ip_address = _get_client_ip(request)
	now = timezone.now()

	with transaction.atomic():
		ip_security, _ = LoginIPBlock.objects.select_for_update().get_or_create(ip_address=ip_address or "0.0.0.0")
		if ip_security.blocked_until and ip_security.blocked_until > now:
			retry_after = int((ip_security.blocked_until - now).total_seconds())
			return True, max(retry_after, 1)

		if ip_security.blocked_until and ip_security.blocked_until <= now:
			ip_security.blocked_until = None
			ip_security.save(update_fields=["blocked_until", "updated_at"])

	return False, 0


def _register_ip_failure(request, role_key):
	ip_address = _get_client_ip(request)
	now = timezone.now()
	window_seconds = getattr(settings, "LOGIN_IP_FAILED_WINDOW_SECONDS", 900)
	limit = getattr(settings, "LOGIN_IP_FAILED_LIMIT", 20)
	block_seconds = getattr(settings, "LOGIN_IP_BLOCK_SECONDS", 900)
	window_start = now - timedelta(seconds=window_seconds)

	with transaction.atomic():
		ip_security, _ = LoginIPBlock.objects.select_for_update().get_or_create(ip_address=ip_address or "0.0.0.0")
		if not ip_security.first_failed_at or ip_security.first_failed_at < window_start:
			ip_security.failed_attempts = 0
			ip_security.first_failed_at = now

		ip_security.failed_attempts += 1
		ip_security.last_failed_at = now

		if ip_security.failed_attempts >= limit:
			if not ip_security.blocked_until or ip_security.blocked_until <= now:
				ip_security.blocked_until = now + timedelta(seconds=block_seconds)

		ip_security.save(
			update_fields=[
				"failed_attempts",
				"first_failed_at",
				"last_failed_at",
				"blocked_until",
				"updated_at",
			]
		)


def _clear_ip_failures(request, role_key):
	ip_address = _get_client_ip(request)
	if not ip_address:
		return

	LoginIPBlock.objects.filter(ip_address=ip_address).update(
		failed_attempts=0,
		first_failed_at=None,
		last_failed_at=None,
		blocked_until=None,
		updated_at=timezone.now(),
	)


def _record_suspicious_activity(*, event_type, ip_address=None, username="", observed_count=0, threshold=0, window_seconds=900):
	now = timezone.now()
	window_start = now - timedelta(seconds=window_seconds)
	with transaction.atomic():
		existing = SuspiciousActivity.objects.select_for_update().filter(
			event_type=event_type,
			ip_address=ip_address,
			username=username,
			last_seen_at__gte=window_start,
		).order_by("-last_seen_at").first()

		if existing:
			existing.sample_count += 1
			existing.observed_count = observed_count
			existing.threshold = threshold
			existing.window_seconds = window_seconds
			existing.details = {
				"event_type": event_type,
				"ip_address": ip_address,
				"username": username,
				"observed_count": observed_count,
				"threshold": threshold,
			}
			existing.save(
				update_fields=[
					"sample_count",
					"observed_count",
					"threshold",
					"window_seconds",
					"details",
					"last_seen_at",
				]
			)
			return

		SuspiciousActivity.objects.create(
			event_type=event_type,
			ip_address=ip_address,
			username=username,
			window_seconds=window_seconds,
			threshold=threshold,
			observed_count=observed_count,
			details={
				"event_type": event_type,
				"ip_address": ip_address,
				"username": username,
				"observed_count": observed_count,
				"threshold": threshold,
			},
		)


def _detect_suspicious_patterns(*, username, ip_address):
	window_seconds = getattr(settings, "LOGIN_SUSPICIOUS_WINDOW_SECONDS", 900)
	window_start = timezone.now() - timedelta(seconds=window_seconds)

	if ip_address:
		ip_username_threshold = getattr(settings, "LOGIN_SUSPICIOUS_IP_USERNAMES_THRESHOLD", 5)
		distinct_usernames = (
			LoginAttemptLog.objects.filter(
				is_successful=False,
				attempted_at__gte=window_start,
				ip_address=ip_address,
			)
			.exclude(username="")
			.values("username")
			.distinct()
			.count()
		)
		if distinct_usernames >= ip_username_threshold:
			_record_suspicious_activity(
				event_type=SuspiciousActivity.EventType.ONE_IP_MULTIPLE_USERNAMES,
				ip_address=ip_address,
				username="",
				observed_count=distinct_usernames,
				threshold=ip_username_threshold,
				window_seconds=window_seconds,
			)

	if username:
		username_ip_threshold = getattr(settings, "LOGIN_SUSPICIOUS_USERNAME_IPS_THRESHOLD", 5)
		distinct_ips = (
			LoginAttemptLog.objects.filter(
				is_successful=False,
				attempted_at__gte=window_start,
				username=username,
			)
			.exclude(ip_address__isnull=True)
			.values("ip_address")
			.distinct()
			.count()
		)
		if distinct_ips >= username_ip_threshold:
			_record_suspicious_activity(
				event_type=SuspiciousActivity.EventType.ONE_USERNAME_MULTIPLE_IPS,
				ip_address=None,
				username=username,
				observed_count=distinct_ips,
				threshold=username_ip_threshold,
				window_seconds=window_seconds,
			)


def _record_login_attempt(
	request,
	*,
	username,
	role_key,
	user=None,
	is_successful=False,
	failure_reason="",
	is_lock_event=False,
	is_unlock_event=False,
	unlocked_by=None,
	unlock_reason="",
):
	user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:512]
	browser, operating_system = _extract_browser_and_os(user_agent)
	LoginAttemptLog.objects.create(
		user=user,
		username=(username or "")[:150],
		ip_address=_get_client_ip(request),
		user_agent=user_agent,
		browser=browser,
		operating_system=operating_system,
		is_successful=is_successful,
		failure_reason=failure_reason,
		role_key=role_key,
		is_lock_event=is_lock_event,
		is_unlock_event=is_unlock_event,
		unlocked_by=unlocked_by,
		unlock_reason=unlock_reason[:255],
	)


def _get_or_create_security_for_update(user):
	security, _ = LoginSecurity.objects.select_for_update().get_or_create(user=user)
	return security


def _is_user_locked(request, *, user, username, role_key):
	with transaction.atomic():
		security = _get_or_create_security_for_update(user)
		if not security.is_locked:
			return False
		_register_ip_failure(request, role_key)
		_record_login_attempt(
			request,
			username=username,
			role_key=role_key,
			user=user,
			is_successful=False,
			failure_reason="locked_account",
		)
		return True


def _register_failed_login(request, *, username, role_key, user=None, failure_reason="invalid_credentials"):
	now = timezone.now()
	locked = False
	client_ip = _get_client_ip(request)
	_register_ip_failure(request, role_key)

	if user is None:
		_record_login_attempt(
			request,
			username=username,
			role_key=role_key,
			is_successful=False,
			failure_reason=failure_reason,
		)
		_detect_suspicious_patterns(username=username, ip_address=client_ip)
		return False

	with transaction.atomic():
		security = _get_or_create_security_for_update(user)
		security.failed_login_attempts += 1
		security.last_failed_login = now
		security.last_failed_ip = client_ip
		just_locked = False
		if security.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
			security.is_locked = True
			if security.locked_at is None:
				security.locked_at = now
				just_locked = True
			locked = True

		security.save(
			update_fields=[
				"failed_login_attempts",
				"last_failed_login",
				"last_failed_ip",
				"is_locked",
				"locked_at",
				"updated_at",
			]
		)
		_record_login_attempt(
			request,
			username=username,
			role_key=role_key,
			user=user,
			is_successful=False,
			failure_reason=failure_reason,
		)
		if just_locked:
			_record_login_attempt(
				request,
				username=username,
				role_key=role_key,
				user=user,
				is_successful=False,
				failure_reason="account_locked",
				is_lock_event=True,
			)

	_detect_suspicious_patterns(username=username, ip_address=client_ip)

	return locked


def _register_successful_login(request, *, username, role_key, user):
	now = timezone.now()
	client_ip = _get_client_ip(request)
	with transaction.atomic():
		security = _get_or_create_security_for_update(user)
		security.failed_login_attempts = 0
		security.is_locked = False
		security.locked_at = None
		security.last_successful_login = now
		security.last_successful_ip = client_ip
		security.save(
			update_fields=[
				"failed_login_attempts",
				"is_locked",
				"locked_at",
				"last_successful_login",
				"last_successful_ip",
				"updated_at",
			]
		)
		_clear_ip_failures(request, role_key)
		_record_login_attempt(
			request,
			username=username,
			role_key=role_key,
			user=user,
			is_successful=True,
		)


@require_http_methods(["GET", "POST"])
def role_login(request, role_key):
	if role_key not in ROLE_CONFIG:
		return redirect("home")

	config = ROLE_CONFIG[role_key]

	if request.user.is_authenticated and _user_has_role_access(request.user, role_key):
		return redirect(config["redirect_name"])

	if request.method == "POST":
		username = request.POST.get("username", "").strip()
		password = request.POST.get("password", "")
		User = get_user_model()
		candidate_user = User.objects.filter(username=username).first() if username else None

		is_rate_limited, retry_after = _is_ip_rate_limited(request, role_key)
		if is_rate_limited:
			_record_login_attempt(
				request,
				username=username,
				role_key=role_key,
				user=candidate_user,
				is_successful=False,
				failure_reason="ip_rate_limited",
			)
			_detect_suspicious_patterns(username=username, ip_address=_get_client_ip(request))
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			response = _render_role_template(request, role_key, status=429)
			response["Retry-After"] = str(retry_after)
			return response

		if not username or not password:
			_register_failed_login(
				request,
				username=username,
				role_key=role_key,
				user=candidate_user,
				failure_reason="invalid_credentials",
			)
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			return _render_role_template(request, role_key)

		if candidate_user and _is_user_locked(
			request,
			user=candidate_user,
			username=username,
			role_key=role_key,
		):
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			return _render_role_template(request, role_key)

		user = authenticate(request, username=username, password=password)

		if user is None:
			_register_failed_login(
				request,
				username=username,
				role_key=role_key,
				user=candidate_user,
				failure_reason="invalid_credentials",
			)
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			return _render_role_template(request, role_key)

		if not user.is_active:
			_register_failed_login(
				request,
				username=username,
				role_key=role_key,
				user=user,
				failure_reason="inactive_account",
			)
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			return _render_role_template(request, role_key)

		if not _user_has_role_access(user, role_key):
			_register_failed_login(
				request,
				username=username,
				role_key=role_key,
				user=user,
				failure_reason="role_access_denied",
			)
			messages.error(request, GENERIC_AUTH_ERROR_MESSAGE)
			return _render_role_template(request, role_key)

		_register_successful_login(
			request,
			username=username,
			role_key=role_key,
			user=user,
		)
		login(request, user)
		request.session.cycle_key()
		return redirect(config["redirect_name"])

	return _render_role_template(request, role_key)


def admin_dashboard(request):
	if not request.user.is_authenticated:
		return redirect("administrator_login")
	if not _user_has_role_access(request.user, "administrator"):
		messages.error(request, "ليس لديك صلاحية الوصول إلى لوحة الإدارة")
		return redirect("administrator_login")

	StudentSubscription.objects.auto_expire()

	students_qs = Student.objects.select_related("account", "account__user")
	teachers_qs = Teacher.objects.select_related("account", "account__user")
	pending_payments_qs = Payment.objects.select_related(
		"student",
		"student__account",
		"student__account__user",
	).filter(status=Payment.Status.PENDING)
	notifications_qs = Notification.objects.for_user(request.user)
	unread_notifications = notifications_qs.filter(status=Notification.Status.UNREAD).count()
	shared_stats = _get_dashboard_shared_stats()
	exams_qs = Exam.objects.select_related("course", "teacher", "teacher__account", "teacher__account__user")
	recent_exams = exams_qs.order_by("-created_at")[:10]
	exam_attempts_qs = StudentExam.objects.select_related("exam", "student")
	exam_summary = exams_qs.aggregate(
		total_exams=Count("id"),
		published_exams=Count("id", filter=Q(status=Exam.Status.PUBLISHED)),
	)
	exam_attempt_summary = exam_attempts_qs.aggregate(
		submitted_exam_attempts=Count(
			"id",
			filter=Q(status__in=[StudentExam.Status.SUBMITTED, StudentExam.Status.GRADED]),
		),
		graded_exam_attempts=Count("id", filter=Q(status=StudentExam.Status.GRADED)),
		pending_exam_grading=Count("id", filter=Q(result_status=StudentExam.ResultStatus.PENDING)),
	)

	context = {
		"total_students": shared_stats["total_students"],
		"total_teachers": shared_stats["total_teachers"],
		"active_teachers": shared_stats["active_teachers"],
		"total_revenue": shared_stats["total_revenue"],
		"published_courses": shared_stats["published_courses"],
		"active_subscriptions": shared_stats["active_subscriptions"],
		"students": students_qs.order_by("-created_at")[:20],
		"teachers": teachers_qs.order_by("-created_at")[:20],
		"pending_payments": pending_payments_qs.order_by("-created_at")[:20],
		"notifications": notifications_qs.order_by("-created_at")[:20],
		"unread_notifications": unread_notifications,
		"recent_activity_logs": ActivityLog.objects.select_related("actor")[:20],
		"total_exams": exam_summary["total_exams"],
		"published_exams": exam_summary["published_exams"],
		"submitted_exam_attempts": exam_attempt_summary["submitted_exam_attempts"],
		"graded_exam_attempts": exam_attempt_summary["graded_exam_attempts"],
		"pending_exam_grading": exam_attempt_summary["pending_exam_grading"],
		"recent_exams": recent_exams,
	}

	return render(request, "admin.html", context)


def teacher_dashboard(request):
	if not request.user.is_authenticated:
		return redirect("teacher_login")
	if not _user_has_role_access(request.user, "teacher"):
		messages.error(request, "ليس لديك صلاحية الوصول إلى لوحة المعلم")
		return redirect("teacher_login")

	teacher_profile = Teacher.objects.select_related("account", "account__user").filter(
		account__user=request.user
	).first()

	if not teacher_profile:
		messages.error(request, "لا يوجد ملف معلم مرتبط بهذا الحساب")
		return redirect("home")

	assigned_courses = list(
		Course.objects.select_related("category")
		.filter(teacher=teacher_profile)
		.order_by("code")
	)
	enrollments = Enrollment.objects.select_related(
		"student",
		"student__account",
		"student__account__user",
		"course",
		"course__category",
	).filter(course__teacher=teacher_profile)

	assigned_students = list(
		Student.objects.select_related("account", "account__user")
		.filter(enrollments__course__teacher=teacher_profile)
		.distinct()
		.order_by("student_code")
	)

	enrollment_stats = enrollments.aggregate(
		avg=Coalesce(Avg("progress_percent"), Value(0.0, output_field=FloatField())),
		total=Count("id"),
		active=Count("id", filter=Q(status=Enrollment.Status.ACTIVE)),
		completed=Count("id", filter=Q(status=Enrollment.Status.COMPLETED)),
		dropped=Count("id", filter=Q(status=Enrollment.Status.DROPPED)),
		suspended=Count("id", filter=Q(status=Enrollment.Status.SUSPENDED)),
	)
	attendance_rate = round(float(enrollment_stats["avg"]), 1)
	attendance_summary = {
		"total": enrollment_stats["total"],
		"active": enrollment_stats["active"],
		"completed": enrollment_stats["completed"],
		"dropped": enrollment_stats["dropped"],
		"suspended": enrollment_stats["suspended"],
	}

	notifications_qs = Notification.objects.for_user(request.user)
	notifications = notifications_qs.order_by("-created_at")[:20]
	unread_notifications = notifications_qs.filter(status=Notification.Status.UNREAD).count()
	teacher_exams_qs = Exam.objects.select_related("course").filter(teacher=teacher_profile)
	teacher_student_exams_qs = StudentExam.objects.select_related("exam", "student", "student__account", "student__account__user").filter(
		exam__teacher=teacher_profile
	)
	teacher_exam_summary = teacher_exams_qs.aggregate(
		total_exams=Count("id"),
		published_exams=Count("id", filter=Q(status=Exam.Status.PUBLISHED)),
	)
	teacher_attempt_summary = teacher_student_exams_qs.aggregate(
		submitted_exam_attempts=Count(
			"id",
			filter=Q(status__in=[StudentExam.Status.SUBMITTED, StudentExam.Status.GRADED]),
		),
		graded_exam_attempts=Count("id", filter=Q(status=StudentExam.Status.GRADED)),
		pending_exam_grading=Count("id", filter=Q(result_status=StudentExam.ResultStatus.PENDING)),
	)

	context = {
		"teacher": teacher_profile,
		"assigned_courses": assigned_courses,
		"assigned_students": assigned_students,
		"enrollments": enrollments[:40],
		"notifications": notifications,
		"attendance_rate": attendance_rate,
		"attendance_summary": attendance_summary,
		"total_courses": len(assigned_courses),
		"total_students": len(assigned_students),
		"active_notifications": unread_notifications,
		"total_exams": teacher_exam_summary["total_exams"],
		"published_exams": teacher_exam_summary["published_exams"],
		"submitted_exam_attempts": teacher_attempt_summary["submitted_exam_attempts"],
		"graded_exam_attempts": teacher_attempt_summary["graded_exam_attempts"],
		"pending_exam_grading": teacher_attempt_summary["pending_exam_grading"],
		"recent_exam_attempts": teacher_student_exams_qs.order_by("-submitted_at", "-created_at")[:20],
	}

	return render(request, "teacher.html", context)


def student_dashboard(request):
	if not request.user.is_authenticated:
		return redirect("student_login")
	if not _user_has_role_access(request.user, "student"):
		messages.error(request, "ليس لديك صلاحية الوصول إلى بوابة الطالب")
		return redirect("student_login")

	StudentSubscription.objects.auto_expire()

	student_profile = Student.objects.select_related("account", "account__user").filter(
		account__user=request.user
	).first()

	if not student_profile:
		messages.error(request, "لا يوجد ملف طالب مرتبط بهذا الحساب")
		return redirect("home")

	subscriptions_qs = StudentSubscription.objects.select_related("plan").filter(
		student=student_profile
	).order_by("-started_at")

	active_subscription = subscriptions_qs.filter(
		status__in=[
			StudentSubscription.Status.ACTIVE,
			StudentSubscription.Status.PENDING,
			StudentSubscription.Status.TRIAL,
		]
	).first()
	subscriptions = list(subscriptions_qs[:20])
	active_subscriptions_count = subscriptions_qs.filter(
		status=StudentSubscription.Status.ACTIVE
	).count()

	enrollments = Enrollment.objects.select_related(
		"course",
		"course__category",
		"course__teacher",
		"course__teacher__account",
		"course__teacher__account__user",
	).filter(student=student_profile).order_by("-enrolled_at")

	enrollment_summary = enrollments.aggregate(
		total_courses=Count("course", distinct=True),
		progress_avg=Coalesce(Avg("progress_percent"), Value(0.0, output_field=FloatField())),
		homework_pending_count=Count(
			"id",
			filter=Q(progress_percent__lt=100) & ~Q(status=Enrollment.Status.DROPPED),
		),
	)

	# No dedicated homework model exists yet; use course progress as practical homework follow-up.
	homework_items_qs = enrollments.exclude(status=Enrollment.Status.DROPPED).order_by("progress_percent", "enrolled_at")
	homework_items = list(homework_items_qs[:20])
	homework_pending_count = enrollment_summary["homework_pending_count"]

	homework_submissions_qs = HomeworkSubmission.objects.select_related(
		"enrollment",
		"enrollment__student",
		"enrollment__course",
	).filter(enrollment__student=student_profile).order_by("-submitted_at")
	homework_submissions = list(homework_submissions_qs[:20])
	homework_submissions_count = homework_submissions_qs.count()

	notifications_qs = Notification.objects.for_user(request.user)
	notifications = notifications_qs.order_by("-created_at")[:20]
	unread_notifications = notifications_qs.filter(status=Notification.Status.UNREAD).count()

	progress_avg = enrollment_summary["progress_avg"]
	progress_rate = round(float(progress_avg), 1)

	student_exams_qs = StudentExam.objects.select_related("exam", "exam__course").filter(student=student_profile)
	available_exams_qs = (
		Exam.objects.filter(
			status=Exam.Status.PUBLISHED,
			course__enrollments__student=student_profile,
		)
		.select_related("course", "teacher", "teacher__account", "teacher__account__user")
		.distinct()
	)
	student_exam_summary = student_exams_qs.aggregate(
		submitted_exam_count=Count(
			"id",
			filter=Q(status__in=[StudentExam.Status.SUBMITTED, StudentExam.Status.GRADED]),
		),
		graded_exam_count=Count("id", filter=Q(status=StudentExam.Status.GRADED)),
		pending_exam_count=Count("id", filter=Q(result_status=StudentExam.ResultStatus.PENDING)),
		exam_average_percentage=Coalesce(
			Avg("percentage", filter=Q(status=StudentExam.Status.GRADED)),
			Value(0, output_field=DecimalField(max_digits=5, decimal_places=2)),
		),
	)
	graded_exam_average = student_exam_summary["exam_average_percentage"]
	graded_exam_average = round(float(graded_exam_average), 1)

	context = {
		"student": student_profile,
		"subscriptions": subscriptions,
		"active_subscription": active_subscription,
		"enrollments": enrollments,
		"homework_items": homework_items,
		"homework_submissions": homework_submissions,
		"notifications": notifications,
		"total_courses": enrollment_summary["total_courses"],
		"active_subscriptions_count": active_subscriptions_count,
		"homework_pending_count": homework_pending_count,
		"homework_submissions_count": homework_submissions_count,
		"unread_notifications": unread_notifications,
		"progress_rate": progress_rate,
		"available_exam_count": available_exams_qs.count(),
		"submitted_exam_count": student_exam_summary["submitted_exam_count"],
		"graded_exam_count": student_exam_summary["graded_exam_count"],
		"pending_exam_count": student_exam_summary["pending_exam_count"],
		"exam_average_percentage": graded_exam_average,
		"available_exams": list(available_exams_qs.order_by("start_at", "created_at")[:10]),
		"recent_student_exams": list(student_exams_qs.order_by("-submitted_at", "-created_at")[:10]),
		"today": timezone.now(),
	}

	return render(request, "student.html", context)


@require_http_methods(["GET", "POST"])
def profile_photo_upload(request):
	if not request.user.is_authenticated:
		messages.error(request, "يرجى تسجيل الدخول أولاً")
		return redirect("home")

	profile = AccountProfile.objects.select_related("user").filter(user=request.user).first()
	if not profile:
		messages.error(request, "لا يوجد ملف شخصي مرتبط بهذا الحساب")
		return redirect("home")

	if request.method == "POST":
		form = ProfilePhotoForm(request.POST, request.FILES, instance=profile)
		if form.is_valid():
			form.save()
			messages.success(request, "تم رفع صورة الملف الشخصي بنجاح")
			return redirect("accounts:profile_photo_upload")
	else:
		form = ProfilePhotoForm(instance=profile)

	context = {
		"form": form,
		"profile": profile,
	}
	return render(request, "profile-photo-upload.html", context)


def parent_dashboard(request):
	if not request.user.is_authenticated:
		return redirect("parent_login")
	if not _user_has_role_access(request.user, "parent"):
		messages.error(request, "ليس لديك صلاحية الوصول إلى بوابة ولي الأمر")
		return redirect("parent_login")

	account_profile = AccountProfile.objects.select_related("user").filter(user=request.user).first()
	notifications_qs = Notification.objects.for_user(request.user)
	notifications = notifications_qs.order_by("-created_at")[:20]
	unread_notifications = notifications_qs.filter(status=Notification.Status.UNREAD).count()
	shared_stats = _get_dashboard_shared_stats()

	context = {
		"profile": account_profile,
		"notifications": notifications,
		"unread_notifications": unread_notifications,
		"total_students": shared_stats["total_students"],
		"total_teachers": shared_stats["total_teachers"],
		"total_courses": Course.objects.count(),
		"active_subscriptions": shared_stats["active_subscriptions"],
	}

	return render(request, "parent.html", context)


@require_http_methods(["POST"])
def logout_view(request):
	if request.user.is_authenticated:
		_record_login_attempt(
			request,
			username=request.user.username,
			role_key="logout",
			user=request.user,
			is_successful=True,
			failure_reason="logout",
		)
	logout(request)
	request.session.flush()
	messages.success(request, "تم تسجيل الخروج بنجاح")
	return redirect("home")


class AccountProfileListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = AccountProfile
	permission_required = "accounts.view_accountprofile"
	template_name = "accounts/accountprofile_list.html"
	context_object_name = "profiles"
	paginate_by = 25

	def get_queryset(self):
		return AccountProfile.objects.select_related("user")


class AccountProfileDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = AccountProfile
	permission_required = "accounts.view_accountprofile"
	template_name = "accounts/accountprofile_detail.html"
	context_object_name = "profile"


class AccountProfileCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = AccountProfile
	form_class = AccountProfileForm
	permission_required = "accounts.add_accountprofile"
	template_name = "accounts/accountprofile_form.html"
	success_url = reverse_lazy("accounts:profile_list")


class AccountProfileUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = AccountProfile
	form_class = AccountProfileForm
	permission_required = "accounts.change_accountprofile"
	template_name = "accounts/accountprofile_form.html"
	success_url = reverse_lazy("accounts:profile_list")


class AccountProfileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = AccountProfile
	permission_required = "accounts.delete_accountprofile"
	template_name = "accounts/accountprofile_confirm_delete.html"
	success_url = reverse_lazy("accounts:profile_list")


def _filtered_activity_logs_queryset(request):
	queryset = ActivityLog.objects.select_related("actor")
	event_type = request.GET.get("event_type", "").strip()
	if event_type:
		queryset = queryset.filter(event_type=event_type)
	return queryset


class ActivityLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = ActivityLog
	permission_required = "accounts.view_accountprofile"
	template_name = "accounts/activitylog_list.html"
	context_object_name = "activity_logs"
	paginate_by = 50

	def get_queryset(self):
		return _filtered_activity_logs_queryset(self.request)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["selected_event_type"] = self.request.GET.get("event_type", "").strip()
		context["event_type_choices"] = ActivityLog.EventType.choices
		return context


class ActivityLogExportCsvView(LoginRequiredMixin, PermissionRequiredMixin, View):
	permission_required = "accounts.view_accountprofile"

	def get(self, request, *args, **kwargs):
		logs = _filtered_activity_logs_queryset(request)

		response = HttpResponse(content_type="text/csv; charset=utf-8")
		response["Content-Disposition"] = 'attachment; filename="activity-logs.csv"'
		response.write("\ufeff")

		writer = csv.writer(response)
		writer.writerow(["timestamp", "actor", "event_type", "action", "target_model", "target_id", "ip_address", "description"])

		for log in logs.iterator():
			writer.writerow(
				[
					log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
					log.actor.username if log.actor else "system",
					log.get_event_type_display(),
					log.action,
					log.target_model,
					log.target_id,
					log.ip_address or "",
					log.description or "",
				]
			)

		return response


class ActivityLogExportExcelView(LoginRequiredMixin, PermissionRequiredMixin, View):
	permission_required = "accounts.view_accountprofile"

	def get(self, request, *args, **kwargs):
		logs = _filtered_activity_logs_queryset(request)

		response = HttpResponse(content_type="application/vnd.ms-excel; charset=utf-8")
		response["Content-Disposition"] = 'attachment; filename="activity-logs.xls"'

		def _clean(value):
			text = str(value or "")
			return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")

		rows = [
			["timestamp", "actor", "event_type", "action", "target_model", "target_id", "ip_address", "description"],
		]

		for log in logs.iterator():
			rows.append(
				[
					log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
					log.actor.username if log.actor else "system",
					log.get_event_type_display(),
					log.action,
					log.target_model,
					log.target_id,
					log.ip_address or "",
					log.description or "",
				]
			)

		for row in rows:
			response.write("\t".join(_clean(cell) for cell in row) + "\n")

		return response
