from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta

from django.contrib import messages
from django.core.cache import cache
from django.db.models import Avg, Count, DecimalField, FloatField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView
from django.utils import timezone

from accounts.permissions import user_has_custom_permission
from courses.models import Course, Enrollment
from exams.models import Exam, StudentExam
from payments.models import Payment
from students.models import Student
from subscriptions.models import StudentSubscription
from teachers.models import Teacher


HOMEPAGE_STATS_CACHE_KEY = "dashboard:homepage:stats:v1"
HOMEPAGE_STATS_CACHE_TIMEOUT = 60
REPORT_PAYLOAD_CACHE_KEY = "dashboard:reports:payload:v1"
REPORT_PAYLOAD_CACHE_TIMEOUT = 300


def _can_manage_all_search_results(user):
	return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff or user.groups.filter(name="Administrator").exists()))


def _student_profile_for_user(user):
	return Student.objects.select_related("account", "account__user").filter(account__user=user).first()


def _teacher_profile_for_user(user):
	return Teacher.objects.select_related("account", "account__user").filter(account__user=user).first()


def _dashboard_route_name_for_user(user):
	if not user or not user.is_authenticated:
		return "home"
	if _can_manage_all_search_results(user):
		return "admin_dashboard"
	if _teacher_profile_for_user(user):
		return "teacher_dashboard"
	if _student_profile_for_user(user):
		return "student_dashboard"
	return "parent_dashboard"


def _build_homepage_stats():
	return {
		"total_students": Student.objects.count(),
		"total_teachers": Teacher.objects.count(),
		"total_courses": Course.objects.count(),
		"total_enrollments": Enrollment.objects.count(),
		"active_subscriptions": StudentSubscription.objects.filter(
			status=StudentSubscription.Status.ACTIVE
		).count(),
		"successful_payments": Payment.objects.filter(
			status=Payment.Status.SUCCESSFUL
		).count(),
	}


class HomePageView(TemplateView):
	template_name = "index.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)

		homepage_stats = cache.get(HOMEPAGE_STATS_CACHE_KEY)
		if homepage_stats is None:
			homepage_stats = _build_homepage_stats()
			cache.set(HOMEPAGE_STATS_CACHE_KEY, homepage_stats, HOMEPAGE_STATS_CACHE_TIMEOUT)

		context.update(homepage_stats)
		return context


GLOBAL_SEARCH_ACCESS_CODES = [
	"access.portal.administrator",
	"access.portal.teacher",
	"access.portal.student",
	"access.portal.parent",
]


def _can_use_global_search(user):
	if not user.is_authenticated or not user.is_active:
		return False
	if user.is_superuser:
		return True
	return any(user_has_custom_permission(user, code) for code in GLOBAL_SEARCH_ACCESS_CODES)


@require_GET
def global_search(request):
	if not request.user.is_authenticated:
		messages.error(request, "يرجى تسجيل الدخول للوصول إلى البحث الشامل")
		return redirect("home")

	if not _can_use_global_search(request.user):
		messages.error(request, "لا تملك صلاحية استخدام البحث الشامل")
		return redirect("home")

	query = request.GET.get("q", "").strip()

	students = Student.objects.none()
	teachers = Teacher.objects.none()
	courses = Course.objects.none()
	payments = Payment.objects.none()
	student_profile = _student_profile_for_user(request.user)
	teacher_profile = _teacher_profile_for_user(request.user)
	can_manage_all_results = _can_manage_all_search_results(request.user)

	if query:
		student_queryset = Student.objects.select_related("account", "account__user")
		teacher_queryset = Teacher.objects.select_related("account", "account__user")
		course_queryset = Course.objects.select_related(
			"category",
			"teacher",
			"teacher__account",
			"teacher__account__user",
		)
		payment_queryset = Payment.objects.select_related(
			"student",
			"student__account",
			"student__account__user",
			"invoice",
			"receipt",
		)

		if can_manage_all_results:
			pass
		elif teacher_profile:
			student_queryset = student_queryset.filter(enrollments__course__teacher=teacher_profile).distinct()
			teacher_queryset = teacher_queryset.filter(pk=teacher_profile.pk)
			course_queryset = course_queryset.filter(teacher=teacher_profile)
			payment_queryset = payment_queryset.none()
		elif student_profile:
			student_queryset = student_queryset.filter(pk=student_profile.pk)
			teacher_queryset = teacher_queryset.filter(courses__enrollments__student=student_profile).distinct()
			course_queryset = course_queryset.filter(enrollments__student=student_profile).distinct()
			payment_queryset = payment_queryset.filter(student=student_profile)
		else:
			student_queryset = student_queryset.none()
			teacher_queryset = teacher_queryset.none()
			course_queryset = course_queryset.filter(status=Course.Status.PUBLISHED)
			payment_queryset = payment_queryset.none()

		students = list(student_queryset.filter(
			Q(student_code__icontains=query)
			| Q(account__user__username__icontains=query)
			| Q(account__user__first_name__icontains=query)
			| Q(account__user__last_name__icontains=query)
			| Q(guardian_name__icontains=query)
			| Q(guardian_phone__icontains=query)
		).order_by("student_code")[:20])

		teachers = list(teacher_queryset.filter(
			Q(employee_code__icontains=query)
			| Q(account__user__username__icontains=query)
			| Q(account__user__first_name__icontains=query)
			| Q(account__user__last_name__icontains=query)
			| Q(specialization__icontains=query)
		).order_by("employee_code")[:20])

		courses = list(course_queryset.filter(
			Q(code__icontains=query)
			| Q(title__icontains=query)
			| Q(description__icontains=query)
			| Q(category__name__icontains=query)
			| Q(teacher__employee_code__icontains=query)
			| Q(teacher__account__user__username__icontains=query)
			| Q(teacher__account__user__first_name__icontains=query)
			| Q(teacher__account__user__last_name__icontains=query)
		).order_by("code")[:20])

		payment_query = (
			Q(transaction_reference__icontains=query)
			| Q(status__icontains=query)
			| Q(method__icontains=query)
			| Q(currency__icontains=query)
			| Q(notes__icontains=query)
			| Q(student__student_code__icontains=query)
			| Q(student__account__user__username__icontains=query)
			| Q(student__account__user__first_name__icontains=query)
			| Q(student__account__user__last_name__icontains=query)
			| Q(invoice__invoice_number__icontains=query)
			| Q(receipt__receipt_number__icontains=query)
		)

		if query.isdigit():
			payment_query |= Q(id=int(query))

		try:
			payment_amount = Decimal(query)
		except (InvalidOperation, ValueError):
			payment_amount = None

		if payment_amount is not None:
			payment_query |= Q(amount=payment_amount)

		payments = list(payment_queryset.filter(payment_query).order_by("-created_at")[:20])

	students_count = len(students) if query else 0
	teachers_count = len(teachers) if query else 0
	courses_count = len(courses) if query else 0
	payments_count = len(payments) if query else 0

	context = {
		"query": query,
		"students": students,
		"teachers": teachers,
		"courses": courses,
		"payments": payments,
		"students_count": students_count,
		"teachers_count": teachers_count,
		"courses_count": courses_count,
		"payments_count": payments_count,
		"total_count": students_count + teachers_count + courses_count + payments_count,
		"dashboard_url_name": _dashboard_route_name_for_user(request.user),
	}

	return render(request, "global-search.html", context)


def _can_view_reports(user):
	if not user.is_authenticated or not user.is_active:
		return False
	if user.is_superuser:
		return True
	return (
		user.groups.filter(name="Administrator").exists()
		and user.has_perm("accounts.view_accountprofile")
		and user_has_custom_permission(user, "access.portal.administrator")
	)


def _month_start(value):
	return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_month(value):
	if value.month == 12:
		return value.replace(year=value.year + 1, month=1)
	return value.replace(month=value.month + 1)


@require_GET
def reports_dashboard(request):
	if not request.user.is_authenticated:
		messages.error(request, "يرجى تسجيل الدخول للوصول إلى التقارير")
		return redirect("administrator_login")

	if not _can_view_reports(request.user):
		messages.error(request, "ليس لديك صلاحية الوصول إلى صفحة التقارير")
		return redirect("admin_dashboard")

	now = timezone.now()
	this_month_start = _month_start(now)
	start_12_months = this_month_start
	for _ in range(11):
		start_12_months = start_12_months.replace(day=1)
		start_12_months = (start_12_months - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	cache_key = f"{REPORT_PAYLOAD_CACHE_KEY}:{start_12_months.strftime('%Y%m')}"
	report_payload = cache.get(cache_key)
	if report_payload is None:
		payment_summary = Payment.objects.aggregate(
			pending_payments=Count("id", filter=Q(status=Payment.Status.PENDING)),
			successful_payments=Count("id", filter=Q(status=Payment.Status.SUCCESSFUL)),
			successful_revenue=Coalesce(
				Sum("amount", filter=Q(status=Payment.Status.SUCCESSFUL)),
				Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
			),
		)

		exam_summary = {
			"total_exams": Exam.objects.count(),
			"published_exams": Exam.objects.filter(status=Exam.Status.PUBLISHED).count(),
			"submitted_exam_attempts": StudentExam.objects.filter(
				status__in=[StudentExam.Status.SUBMITTED, StudentExam.Status.GRADED]
			).count(),
			"graded_exam_attempts": StudentExam.objects.filter(status=StudentExam.Status.GRADED).count(),
			"pending_exam_grading": StudentExam.objects.filter(
				result_status=StudentExam.ResultStatus.PENDING
			).count(),
		}

		statistics = {
			"total_students": Student.objects.count(),
			"total_teachers": Teacher.objects.count(),
			"total_courses": Course.objects.count(),
			"total_enrollments": Enrollment.objects.count(),
			"active_subscriptions": StudentSubscription.objects.filter(status=StudentSubscription.Status.ACTIVE).count(),
			"pending_payments": payment_summary["pending_payments"],
			"successful_payments": payment_summary["successful_payments"],
			"successful_revenue": payment_summary["successful_revenue"],
			"total_exams": exam_summary["total_exams"],
			"published_exams": exam_summary["published_exams"],
			"submitted_exam_attempts": exam_summary["submitted_exam_attempts"],
			"graded_exam_attempts": exam_summary["graded_exam_attempts"],
			"pending_exam_grading": exam_summary["pending_exam_grading"],
		}

		monthly_payment_qs = (
			Payment.objects.filter(created_at__gte=start_12_months)
			.annotate(month=TruncMonth("created_at"))
			.values("month")
			.annotate(
				payment_count=Count("id"),
				successful_count=Count("id", filter=Q(status=Payment.Status.SUCCESSFUL)),
				successful_amount=Coalesce(
					Sum("amount", filter=Q(status=Payment.Status.SUCCESSFUL)),
					Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
				),
			)
		)

		monthly_student_qs = (
			Student.objects.filter(created_at__gte=start_12_months)
			.annotate(month=TruncMonth("created_at"))
			.values("month")
			.annotate(new_students=Count("id"))
		)

		monthly_enrollment_qs = (
			Enrollment.objects.filter(enrolled_at__gte=start_12_months)
			.annotate(month=TruncMonth("enrolled_at"))
			.values("month")
			.annotate(new_enrollments=Count("id"))
		)

		payment_by_month = {item["month"].date().replace(day=1): item for item in monthly_payment_qs}
		student_by_month = {item["month"].date().replace(day=1): item for item in monthly_student_qs}
		enrollment_by_month = {item["month"].date().replace(day=1): item for item in monthly_enrollment_qs}

		month_cursor = start_12_months
		monthly_report_rows = []
		monthly_labels = []
		monthly_revenue = []
		monthly_payment_counts = []
		monthly_new_students = []
		monthly_new_enrollments = []

		while month_cursor <= this_month_start:
			key = month_cursor.date().replace(day=1)
			payment_row = payment_by_month.get(key, {})
			student_row = student_by_month.get(key, {})
			enrollment_row = enrollment_by_month.get(key, {})

			label = datetime(month_cursor.year, month_cursor.month, 1).strftime("%Y-%m")
			revenue_value = float(payment_row.get("successful_amount") or 0)
			payment_count_value = int(payment_row.get("payment_count") or 0)
			student_count_value = int(student_row.get("new_students") or 0)
			enrollment_count_value = int(enrollment_row.get("new_enrollments") or 0)

			monthly_labels.append(label)
			monthly_revenue.append(revenue_value)
			monthly_payment_counts.append(payment_count_value)
			monthly_new_students.append(student_count_value)
			monthly_new_enrollments.append(enrollment_count_value)

			monthly_report_rows.append(
				{
					"month": label,
					"new_students": student_count_value,
					"new_enrollments": enrollment_count_value,
					"payment_count": payment_count_value,
					"successful_count": int(payment_row.get("successful_count") or 0),
					"successful_amount": payment_row.get("successful_amount") or 0,
				}
			)

			month_cursor = _add_month(month_cursor)

		payment_status_rows = list(
			Payment.objects.values("status")
			.annotate(
				count=Count("id"),
				total_amount=Coalesce(
					Sum("amount"),
					Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
				),
			)
			.order_by("status")
		)

		payment_method_rows = list(
			Payment.objects.values("method")
			.annotate(
				count=Count("id"),
				total_amount=Coalesce(
					Sum("amount"),
					Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
				),
			)
			.order_by("method")
		)

		status_display_map = dict(Payment.Status.choices)
		method_display_map = dict(Payment.Method.choices)

		report_payload = {
			"statistics": statistics,
			"monthly_report_rows": monthly_report_rows,
			"monthly_labels": monthly_labels,
			"monthly_revenue": monthly_revenue,
			"monthly_payment_counts": monthly_payment_counts,
			"monthly_new_students": monthly_new_students,
			"monthly_new_enrollments": monthly_new_enrollments,
			"payment_status_rows": payment_status_rows,
			"payment_method_rows": payment_method_rows,
			"payment_status_labels": [status_display_map.get(item["status"], item["status"]) for item in payment_status_rows],
			"payment_status_counts": [int(item["count"]) for item in payment_status_rows],
			"payment_status_amounts": [float(item["total_amount"] or 0) for item in payment_status_rows],
			"payment_method_labels": [method_display_map.get(item["method"], item["method"]) for item in payment_method_rows],
			"payment_method_counts": [int(item["count"]) for item in payment_method_rows],
			"payment_method_amounts": [float(item["total_amount"] or 0) for item in payment_method_rows],
		}

		cache.set(cache_key, report_payload, REPORT_PAYLOAD_CACHE_TIMEOUT)

	course_reports = (
		Course.objects.select_related("category", "teacher", "teacher__account", "teacher__account__user")
		.annotate(
			enrollment_count=Count("enrollments", distinct=True),
			active_enrollment_count=Count(
				"enrollments",
				filter=Q(enrollments__status=Enrollment.Status.ACTIVE),
				distinct=True,
			),
			avg_progress=Coalesce(
				Avg("enrollments__progress_percent"),
				Value(0.0, output_field=FloatField()),
			),
			successful_payment_total=Coalesce(
				Sum(
					"enrollments__student__payments__amount",
					filter=Q(enrollments__student__payments__status=Payment.Status.SUCCESSFUL),
				),
				Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)),
			),
		)
		.order_by("-enrollment_count", "code")[:25]
	)

	recent_payments = Payment.objects.select_related(
		"student",
		"student__account",
		"student__account__user",
		"invoice",
		"receipt",
	).order_by("-created_at")[:20]

	exam_reports = (
		Exam.objects.select_related("course", "teacher", "teacher__account", "teacher__account__user")
		.annotate(
			question_count=Count("questions", distinct=True),
			submitted_attempts=Count(
				"student_exams",
				filter=Q(student_exams__status__in=[StudentExam.Status.SUBMITTED, StudentExam.Status.GRADED]),
				distinct=True,
			),
			graded_attempts=Count(
				"student_exams",
				filter=Q(student_exams__status=StudentExam.Status.GRADED),
				distinct=True,
			),
			passed_attempts=Count(
				"student_exams",
				filter=Q(student_exams__result_status=StudentExam.ResultStatus.PASSED),
				distinct=True,
			),
			avg_percentage=Coalesce(
				Avg("student_exams__percentage"),
				Value(0, output_field=DecimalField(max_digits=5, decimal_places=2)),
			),
		)
		.order_by("-created_at")[:25]
	)

	context = {
		"statistics": report_payload["statistics"],
		"monthly_report_rows": report_payload["monthly_report_rows"],
		"course_reports": course_reports,
		"payment_status_rows": report_payload["payment_status_rows"],
		"payment_method_rows": report_payload["payment_method_rows"],
		"recent_payments": recent_payments,
		"monthly_labels": report_payload["monthly_labels"],
		"monthly_revenue": report_payload["monthly_revenue"],
		"monthly_payment_counts": report_payload["monthly_payment_counts"],
		"monthly_new_students": report_payload["monthly_new_students"],
		"monthly_new_enrollments": report_payload["monthly_new_enrollments"],
		"payment_status_labels": report_payload["payment_status_labels"],
		"payment_status_counts": report_payload["payment_status_counts"],
		"payment_status_amounts": report_payload["payment_status_amounts"],
		"payment_method_labels": report_payload["payment_method_labels"],
		"payment_method_counts": report_payload["payment_method_counts"],
		"payment_method_amounts": report_payload["payment_method_amounts"],
		"exam_reports": exam_reports,
	}

	return render(request, "reports.html", context)
