from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.http import HttpRequest
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import AccountProfileForm
from accounts.models import (
	AccountProfile,
	ActivityLog,
	CustomPermission,
	LoginAttemptLog,
	LoginIPBlock,
	LoginSecurity,
	RoleCustomPermission,
	SuspiciousActivity,
	UserCustomPermission,
)
from accounts.permissions import user_has_custom_permission
from accounts.views import _register_failed_login
from payments.models import Payment
from notifications.models import Notification
from courses.models import Course, Enrollment
from exams.models import Exam, StudentExam
from students.models import Student
from subscriptions.models import StudentSubscription, SubscriptionPlan
from teachers.models import Teacher


class CleanTestCase(TestCase):
	def tearDown(self):
		# Prevent state leakage between classes that share the same client process.
		self.client.cookies.clear()
		cache.clear()
		super().tearDown()


class CleanTransactionTestCase(TransactionTestCase):
	def tearDown(self):
		self.client.cookies.clear()
		cache.clear()
		super().tearDown()


class CustomPermissionUnitTests(CleanTestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="perm-user", password="StrongPass123")
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		self.permission = CustomPermission.objects.create(
			code="unit.test.permission",
			name="Unit Test Permission",
			is_active=True,
		)

	def test_user_level_deny_overrides_role_grant(self):
		RoleCustomPermission.objects.create(role=self.profile.role, permission=self.permission, is_granted=True)
		UserCustomPermission.objects.create(user=self.user, permission=self.permission, is_granted=False)

		self.assertFalse(user_has_custom_permission(self.user, self.permission.code))

	def test_user_level_grant_overrides_role_deny(self):
		RoleCustomPermission.objects.create(role=self.profile.role, permission=self.permission, is_granted=False)
		UserCustomPermission.objects.create(user=self.user, permission=self.permission, is_granted=True)

		self.assertTrue(user_has_custom_permission(self.user, self.permission.code))


class AuthenticationIntegrationTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.user = User.objects.create_user(username="admin-login", password=self.password)
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		view_profile_perm = Permission.objects.get(codename="view_accountprofile")
		self.user.user_permissions.add(view_profile_perm)

		custom_permission, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={
				"name": "Access Administrator Portal",
				"is_active": True,
			},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=custom_permission,
			defaults={"is_granted": True},
		)

	def test_administrator_login_succeeds_and_creates_login_activity(self):
		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
		)

		self.assertRedirects(response, reverse("admin_dashboard"))
		self.assertTrue(
			ActivityLog.objects.filter(
				actor=self.user,
				event_type=ActivityLog.EventType.LOGIN,
				action="login",
			).exists()
		)

	def test_administrator_login_denied_when_custom_permission_denied(self):
		permission = CustomPermission.objects.get(code="access.portal.administrator")
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=permission,
			defaults={"is_granted": False},
		)

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
		)

		self.assertEqual(response.status_code, 200)
		self.assertNotIn("_auth_user_id", self.client.session)

	def test_administrator_login_rotates_session_id(self):
		session = self.client.session
		session["pre_login"] = "marker"
		session.save()
		old_session_key = session.session_key

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
		)

		self.assertEqual(response.status_code, 302)
		self.assertNotEqual(old_session_key, self.client.session.session_key)


class ActivityLogSignalIntegrationTests(CleanTestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="signal-user", password="StrongPass123")
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=self.profile,
			student_code="STU-SIGNAL-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		ActivityLog.objects.all().delete()

	def test_student_edit_and_delete_create_activity_logs(self):
		self.student.status = Student.Status.BLOCKED
		self.student.save()
		student_id = self.student.pk
		self.student.delete()

		self.assertTrue(
			ActivityLog.objects.filter(
				event_type=ActivityLog.EventType.EDIT,
				action="edit",
				target_model="students.Student",
				target_id=str(student_id),
			).exists()
		)
		self.assertTrue(
			ActivityLog.objects.filter(
				event_type=ActivityLog.EventType.DELETE,
				action="delete",
				target_model="students.Student",
				target_id=str(student_id),
			).exists()
		)

	def test_payment_create_edit_delete_create_payment_activity_logs(self):
		payment = Payment.objects.create(
			student=self.student,
			requested_by=self.user,
			amount="15000.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-SIGNAL-001",
		)
		payment_id = payment.pk

		payment.notes = "edited"
		payment.save()
		payment.delete()

		self.assertTrue(
			ActivityLog.objects.filter(
				event_type=ActivityLog.EventType.PAYMENT,
				action="create",
				target_model="payments.Payment",
				target_id=str(payment_id),
			).exists()
		)
		self.assertTrue(
			ActivityLog.objects.filter(
				event_type=ActivityLog.EventType.PAYMENT,
				action="edit",
				target_model="payments.Payment",
				target_id=str(payment_id),
			).exists()
		)
		self.assertTrue(
			ActivityLog.objects.filter(
				event_type=ActivityLog.EventType.PAYMENT,
				action="delete",
				target_model="payments.Payment",
				target_id=str(payment_id),
			).exists()
		)


class AccountProfileSignalSyncTests(CleanTestCase):
	def test_role_change_from_admin_revokes_staff_flag(self):
		user = User.objects.create_user(username="role-sync-user", password="StrongPass123", is_staff=False)
		profile = AccountProfile.objects.create(
			user=user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)

		user.refresh_from_db()
		self.assertTrue(user.is_staff)

		profile.role = AccountProfile.Role.STUDENT
		profile.save(update_fields=["role"])

		user.refresh_from_db()
		self.assertFalse(user.is_staff)


class ActivityLogExportIntegrationTests(CleanTestCase):
	def setUp(self):
		self.admin_user = User.objects.create_user(username="export-admin", password="StrongPass123")
		AccountProfile.objects.create(
			user=self.admin_user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		view_profile_perm = Permission.objects.get(codename="view_accountprofile")
		self.admin_user.user_permissions.add(view_profile_perm)
		self.client.force_login(self.admin_user)

		ActivityLog.objects.create(
			actor=self.admin_user,
			event_type=ActivityLog.EventType.LOGIN,
			action="login",
			target_model="auth.User",
			target_id=str(self.admin_user.pk),
			description="Login event",
		)
		ActivityLog.objects.create(
			actor=self.admin_user,
			event_type=ActivityLog.EventType.PAYMENT,
			action="edit",
			target_model="payments.Payment",
			target_id="1",
			description="Payment event",
		)

	def test_csv_export_returns_filtered_rows(self):
		response = self.client.get(
			reverse("accounts:activity_log_export_csv"),
			{"event_type": ActivityLog.EventType.LOGIN},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn("text/csv", response["Content-Type"])
		content = response.content.decode("utf-8")
		self.assertIn("timestamp,actor,event_type,action,target_model,target_id,ip_address,description", content)
		self.assertIn("Login", content)
		self.assertNotIn("Payment event", content)

	def test_excel_export_returns_file_attachment(self):
		response = self.client.get(reverse("accounts:activity_log_export_excel"))

		self.assertEqual(response.status_code, 200)
		self.assertIn("application/vnd.ms-excel", response["Content-Type"])
		self.assertIn("attachment; filename=\"activity-logs.xls\"", response["Content-Disposition"])
		decoded = response.content.decode("utf-8")
		self.assertIn("timestamp\tactor\tevent_type\taction", decoded)


class AuthenticationAndProfileFormTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.user = User.objects.create_user(
			username="profile-user",
			password=self.password,
			email="old@example.com",
		)
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)

	def test_logout_redirects_to_home(self):
		self.client.force_login(self.user)
		response = self.client.post(reverse("logout"))
		self.assertRedirects(response, reverse("home"))

	def test_logout_rejects_get(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("logout"))
		self.assertEqual(response.status_code, 405)

	def test_profile_form_updates_user_email(self):
		form = AccountProfileForm(
			data={
				"user": self.user.pk,
				"user_email": "new@example.com",
				"role": AccountProfile.Role.ADMIN,
				"status": AccountProfile.Status.ACTIVE,
				"phone_number": "+963999999999",
				"country": "Syria",
			},
			instance=self.profile,
		)
		self.assertTrue(form.is_valid())
		form.save()
		self.user.refresh_from_db()
		self.assertEqual(self.user.email, "new@example.com")

	def test_profile_view_permission_can_be_granted(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_accountprofile"))
		self.assertTrue(self.user.has_perm("accounts.view_accountprofile"))

	def test_profile_create_redirects_to_namespaced_list(self):
		creator = User.objects.create_user(
			username="profile-creator",
			password=self.password,
			email="creator@example.com",
		)
		creator.user_permissions.add(Permission.objects.get(codename="add_accountprofile"))
		self.client.force_login(creator)

		target_user = User.objects.create_user(
			username="new-profile-user",
			password=self.password,
			email="new-profile@example.com",
		)

		response = self.client.post(
			reverse("accounts:profile_create"),
			data={
				"user": target_user.pk,
				"user_email": "new-profile@example.com",
				"role": AccountProfile.Role.STUDENT,
				"status": AccountProfile.Status.ACTIVE,
				"phone_number": "+963955555555",
				"country": "Syria",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("accounts:profile_list"))
		self.assertTrue(AccountProfile.objects.filter(user=target_user).exists())



class RemovedPublicRegistrationRouteTests(CleanTestCase):
	def test_old_student_registration_route_is_inaccessible(self):
		response = self.client.get("/student-register/")
		self.assertEqual(response.status_code, 404)

	def test_old_teacher_registration_route_is_inaccessible(self):
		response = self.client.get("/teacher-register/")
		self.assertEqual(response.status_code, 404)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginProtectionIntegrationTests(CleanTestCase):
	def setUp(self):
		cache.clear()
		self.password = "StrongPass123"
		self.user = User.objects.create_user(username="lockout-admin", password=self.password)
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		self.user.user_permissions.add(Permission.objects.get(codename="view_accountprofile"))

		custom_permission, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=custom_permission,
			defaults={"is_granted": True},
		)

	def _failed_login(self):
		return self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": "WrongPass123"},
			HTTP_USER_AGENT="unit-test-agent",
			REMOTE_ADDR="127.0.0.9",
		)

	def test_successful_login_updates_security_and_creates_audit_log(self):
		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
			HTTP_USER_AGENT="unit-test-agent",
			REMOTE_ADDR="127.0.0.10",
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("admin_dashboard"))

		security = LoginSecurity.objects.get(user=self.user)
		self.assertEqual(security.failed_login_attempts, 0)
		self.assertFalse(security.is_locked)
		self.assertIsNone(security.locked_at)
		self.assertIsNotNone(security.last_successful_login)
		self.assertEqual(security.last_successful_ip, "127.0.0.10")

		audit = LoginAttemptLog.objects.filter(user=self.user).first()
		self.assertIsNotNone(audit)
		self.assertTrue(audit.is_successful)
		self.assertEqual(audit.username, self.user.username)
		self.assertEqual(audit.ip_address, "127.0.0.10")
		self.assertNotEqual(audit.browser, "")
		self.assertNotEqual(audit.operating_system, "")

	def test_failed_login_increments_counter_and_logs_attempt(self):
		response = self._failed_login()
		self.assertEqual(response.status_code, 200)

		security = LoginSecurity.objects.get(user=self.user)
		self.assertEqual(security.failed_login_attempts, 1)
		self.assertFalse(security.is_locked)
		self.assertIsNotNone(security.last_failed_login)
		self.assertEqual(security.last_failed_ip, "127.0.0.9")

		audit = LoginAttemptLog.objects.filter(user=self.user).first()
		self.assertIsNotNone(audit)
		self.assertFalse(audit.is_successful)
		self.assertEqual(audit.failure_reason, "invalid_credentials")

	def test_account_locks_after_six_failed_attempts(self):
		for _ in range(6):
			self._failed_login()

		security = LoginSecurity.objects.get(user=self.user)
		self.assertEqual(security.failed_login_attempts, 6)
		self.assertTrue(security.is_locked)
		self.assertIsNotNone(security.locked_at)

		audit = LoginAttemptLog.objects.filter(
			user=self.user,
			username=self.user.username,
			failure_reason="account_locked",
			is_lock_event=True,
		).first()
		self.assertIsNotNone(audit)

	def test_locked_account_cannot_login_with_correct_password(self):
		for _ in range(6):
			self._failed_login()

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
		)

		self.assertEqual(response.status_code, 200)
		self.assertNotIn("_auth_user_id", self.client.session)

		messages = [str(message) for message in response.context["messages"]]
		self.assertIn("بيانات الدخول غير صحيحة", messages)

		audit = LoginAttemptLog.objects.filter(
			user=self.user,
			username=self.user.username,
			failure_reason="locked_account",
		).first()
		self.assertIsNotNone(audit)
		self.assertFalse(audit.is_successful)
		self.assertFalse(audit.is_lock_event)

	def test_successful_login_resets_counter(self):
		for _ in range(2):
			self._failed_login()

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
		)
		self.assertEqual(response.status_code, 302)

		security = LoginSecurity.objects.get(user=self.user)
		self.assertEqual(security.failed_login_attempts, 0)
		self.assertFalse(security.is_locked)
		self.assertIsNone(security.locked_at)

	def test_admin_unlock_reset_flow(self):
		for _ in range(6):
			self._failed_login()

		security = LoginSecurity.objects.get(user=self.user)
		security.failed_login_attempts = 0
		security.is_locked = False
		security.locked_at = None
		security.save(update_fields=["failed_login_attempts", "is_locked", "locked_at", "updated_at"])

		security.refresh_from_db()
		self.assertEqual(security.failed_login_attempts, 0)
		self.assertFalse(security.is_locked)
		self.assertIsNone(security.locked_at)

	def test_generic_error_does_not_reveal_username_existence(self):
		response = self.client.post(
			reverse("administrator_login"),
			data={"username": "unknown-user-123", "password": "WrongPass123"},
		)
		self.assertEqual(response.status_code, 200)
		messages = [str(message) for message in response.context["messages"]]
		self.assertIn("بيانات الدخول غير صحيحة", messages)


class LoginSecurityAdminPermissionTests(CleanTestCase):
	def setUp(self):
		self.superuser = User.objects.create_superuser(
			username="super-admin",
			email="super@example.com",
			password="StrongPass123",
		)
		self.staff_without_unlock = User.objects.create_user(
			username="staff-no-unlock",
			password="StrongPass123",
			is_staff=True,
		)
		self.staff_with_unlock = User.objects.create_user(
			username="staff-with-unlock",
			password="StrongPass123",
			is_staff=True,
		)
		view_permission = Permission.objects.get(codename="view_loginsecurity")
		change_permission = Permission.objects.get(codename="change_loginsecurity")
		self.staff_without_unlock.user_permissions.add(view_permission, change_permission)
		self.staff_with_unlock.user_permissions.add(view_permission, change_permission)
		unlock_permission = Permission.objects.get(codename="unlock_loginsecurity")
		self.staff_with_unlock.user_permissions.add(unlock_permission)

		self.target_user = User.objects.create_user(username="locked-user", password="StrongPass123")
		self.security = LoginSecurity.objects.create(
			user=self.target_user,
			failed_login_attempts=6,
			is_locked=True,
		)

	def test_unlock_action_hidden_without_permission(self):
		self.client.force_login(self.staff_without_unlock)
		response = self.client.get(reverse("admin:accounts_loginsecurity_changelist"))
		self.assertEqual(response.status_code, 200)
		action_form = response.context.get("action_form")
		if action_form is None:
			return
		action_choices = action_form.fields["action"].choices
		action_names = {name for name, _ in action_choices if name}
		self.assertNotIn("unlock_accounts", action_names)

	def test_unlock_action_visible_with_permission(self):
		self.client.force_login(self.staff_with_unlock)
		response = self.client.get(reverse("admin:accounts_loginsecurity_changelist"))
		self.assertEqual(response.status_code, 200)
		action_choices = response.context["action_form"].fields["action"].choices
		action_names = {name for name, _ in action_choices if name}
		self.assertIn("unlock_accounts", action_names)

	def test_unlock_action_resets_lock_state(self):
		self.client.force_login(self.staff_with_unlock)
		response = self.client.post(
			reverse("admin:accounts_loginsecurity_changelist"),
			data={
				"action": "unlock_accounts",
				"_selected_action": [str(self.security.pk)],
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.security.refresh_from_db()
		self.assertEqual(self.security.failed_login_attempts, 0)
		self.assertFalse(self.security.is_locked)
		self.assertIsNone(self.security.locked_at)


@override_settings(
	PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
	LOGIN_IP_FAILED_LIMIT=3,
	LOGIN_IP_FAILED_WINDOW_SECONDS=300,
	LOGIN_IP_BLOCK_SECONDS=300,
	LOGIN_SUSPICIOUS_IP_USERNAMES_THRESHOLD=3,
	LOGIN_SUSPICIOUS_USERNAME_IPS_THRESHOLD=3,
	LOGIN_SUSPICIOUS_WINDOW_SECONDS=300,
)
class LoginIpRateLimitingTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.user1 = User.objects.create_user(username="ip-admin-1", password=self.password)
		self.user2 = User.objects.create_user(username="ip-admin-2", password=self.password)
		AccountProfile.objects.create(
			user=self.user1,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		AccountProfile.objects.create(
			user=self.user2,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		view_profile_perm = Permission.objects.get(codename="view_accountprofile")
		self.user1.user_permissions.add(view_profile_perm)
		self.user2.user_permissions.add(view_profile_perm)

		custom_permission, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=custom_permission,
			defaults={"is_granted": True},
		)

	def test_ip_throttling_blocks_after_threshold(self):
		for _ in range(3):
			self.client.post(
				reverse("administrator_login"),
				data={"username": self.user1.username, "password": "WrongPass"},
				REMOTE_ADDR="127.0.0.50",
			)

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user1.username, "password": self.password},
			REMOTE_ADDR="127.0.0.50",
		)

		self.assertEqual(response.status_code, 429)
		self.assertIn("Retry-After", response)
		self.assertNotIn("_auth_user_id", self.client.session)
		ip_block = LoginIPBlock.objects.get(ip_address="127.0.0.50")
		self.assertIsNotNone(ip_block.blocked_until)
		self.assertGreater(ip_block.blocked_until, timezone.now())

	def test_ip_throttling_applies_across_multiple_usernames(self):
		self.client.post(
			reverse("administrator_login"),
			data={"username": self.user1.username, "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.77",
		)
		self.client.post(
			reverse("administrator_login"),
			data={"username": self.user2.username, "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.77",
		)
		self.client.post(
			reverse("administrator_login"),
			data={"username": "unknown-ip-user", "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.77",
		)

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user2.username, "password": self.password},
			REMOTE_ADDR="127.0.0.77",
		)

		self.assertEqual(response.status_code, 429)
		self.assertNotIn("_auth_user_id", self.client.session)

	def test_unknown_usernames_are_counted_in_ip_blocking(self):
		for idx in range(3):
			self.client.post(
				reverse("administrator_login"),
				data={"username": f"unknown-{idx}", "password": "WrongPass"},
				REMOTE_ADDR="127.0.0.79",
			)

		response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user1.username, "password": self.password},
			REMOTE_ADDR="127.0.0.79",
		)

		self.assertEqual(response.status_code, 429)
		self.assertTrue(LoginIPBlock.objects.filter(ip_address="127.0.0.79").exists())

	def test_suspicious_activity_detected_for_multiple_usernames_from_one_ip(self):
		self.client.post(
			reverse("administrator_login"),
			data={"username": self.user1.username, "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.88",
		)
		self.client.post(
			reverse("administrator_login"),
			data={"username": self.user2.username, "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.88",
		)
		self.client.post(
			reverse("administrator_login"),
			data={"username": "suspicious-unknown", "password": "WrongPass"},
			REMOTE_ADDR="127.0.0.88",
		)

		self.assertTrue(
			SuspiciousActivity.objects.filter(
				event_type=SuspiciousActivity.EventType.ONE_IP_MULTIPLE_USERNAMES,
				ip_address="127.0.0.88",
			).exists()
		)
		suspicious = SuspiciousActivity.objects.filter(
			event_type=SuspiciousActivity.EventType.ONE_IP_MULTIPLE_USERNAMES,
			ip_address="127.0.0.88",
		).order_by("-last_seen_at").first()
		self.assertIsNotNone(suspicious)
		self.assertGreaterEqual(suspicious.observed_count, 3)
		self.assertEqual(suspicious.threshold, 3)
		self.assertEqual(suspicious.window_seconds, 300)
		self.assertGreaterEqual(suspicious.sample_count, 1)
		self.assertEqual(suspicious.details.get("event_type"), SuspiciousActivity.EventType.ONE_IP_MULTIPLE_USERNAMES)

	def test_suspicious_activity_detected_for_multiple_ips_against_one_username(self):
		for idx in range(3):
			self.client.post(
				reverse("administrator_login"),
				data={"username": self.user1.username, "password": "WrongPass"},
				REMOTE_ADDR=f"127.0.1.{idx + 1}",
			)

		self.assertTrue(
			SuspiciousActivity.objects.filter(
				event_type=SuspiciousActivity.EventType.ONE_USERNAME_MULTIPLE_IPS,
				username=self.user1.username,
			).exists()
		)
		suspicious = SuspiciousActivity.objects.filter(
			event_type=SuspiciousActivity.EventType.ONE_USERNAME_MULTIPLE_IPS,
			username=self.user1.username,
		).order_by("-last_seen_at").first()
		self.assertIsNotNone(suspicious)
		self.assertGreaterEqual(suspicious.observed_count, 3)
		self.assertEqual(suspicious.threshold, 3)
		self.assertEqual(suspicious.window_seconds, 300)
		self.assertGreaterEqual(suspicious.sample_count, 1)
		self.assertEqual(suspicious.details.get("event_type"), SuspiciousActivity.EventType.ONE_USERNAME_MULTIPLE_IPS)


@override_settings(
	PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
	LOGIN_IP_FAILED_LIMIT=20,
	LOGIN_IP_FAILED_WINDOW_SECONDS=900,
	LOGIN_IP_BLOCK_SECONDS=900,
)
class LoginIpRateLimitPolicyTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.user = User.objects.create_user(username="ip-policy-admin", password=self.password)
		AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		self.user.user_permissions.add(Permission.objects.get(codename="view_accountprofile"))

		custom_permission, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=custom_permission,
			defaults={"is_granted": True},
		)

	def test_tracks_failed_attempts_by_ip_and_blocks_after_20_failures(self):
		target_ip = "127.0.2.20"

		for _ in range(20):
			response = self.client.post(
				reverse("administrator_login"),
				data={"username": self.user.username, "password": "WrongPass"},
				REMOTE_ADDR=target_ip,
			)
			self.assertEqual(response.status_code, 200)

		ip_block = LoginIPBlock.objects.get(ip_address=target_ip)
		self.assertEqual(ip_block.failed_attempts, 20)
		self.assertIsNotNone(ip_block.first_failed_at)
		self.assertIsNotNone(ip_block.last_failed_at)
		self.assertIsNotNone(ip_block.blocked_until)
		self.assertGreater(ip_block.blocked_until, timezone.now())

		blocked_response = self.client.post(
			reverse("administrator_login"),
			data={"username": self.user.username, "password": self.password},
			REMOTE_ADDR=target_ip,
		)

		self.assertEqual(blocked_response.status_code, 429)
		self.assertIn("Retry-After", blocked_response)

	def test_block_window_is_15_minutes(self):
		target_ip = "127.0.2.21"

		for _ in range(20):
			self.client.post(
				reverse("administrator_login"),
				data={"username": self.user.username, "password": "WrongPass"},
				REMOTE_ADDR=target_ip,
			)

		ip_block = LoginIPBlock.objects.get(ip_address=target_ip)
		window_seconds = int((ip_block.blocked_until - ip_block.last_failed_at).total_seconds())
		self.assertGreaterEqual(window_seconds, 895)
		self.assertLessEqual(window_seconds, 905)


class LoginAttemptLogIntegrityTests(CleanTestCase):
	def test_login_attempt_log_is_immutable(self):
		user = User.objects.create_user(username="audit-user", password="StrongPass123")
		audit = LoginAttemptLog.objects.create(
			user=user,
			username=user.username,
			ip_address="127.0.0.88",
			user_agent="Mozilla/5.0",
			browser="Firefox",
			operating_system="Windows",
			is_successful=False,
			failure_reason="invalid_credentials",
			role_key="administrator",
		)

		audit.failure_reason = "edited"
		with self.assertRaises(ValidationError):
			audit.save()

		with self.assertRaises(ValidationError):
			audit.delete()


class LoginIpBlockModelTests(CleanTestCase):
	def test_login_ip_block_str_returns_blocked_when_future_block_exists(self):
		ip_block = LoginIPBlock.objects.create(
			ip_address="127.0.7.1",
			blocked_until=timezone.now() + timedelta(minutes=5),
		)

		self.assertIn("(blocked)", str(ip_block))

	def test_login_ip_block_str_returns_open_when_not_blocked(self):
		ip_block = LoginIPBlock.objects.create(
			ip_address="127.0.7.2",
			blocked_until=timezone.now() - timedelta(minutes=1),
		)

		self.assertIn("(open)", str(ip_block))


class LogoutAndUnlockAuditTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.user = User.objects.create_user(username="logout-audit-user", password=self.password)
		self.profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		self.user.user_permissions.add(Permission.objects.get(codename="view_accountprofile"))
		self.custom_permission, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=self.custom_permission,
			defaults={"is_granted": True},
		)

	def test_logout_creates_login_attempt_log_entry(self):
		self.client.force_login(self.user)
		pre_logout_session_key = self.client.session.session_key
		response = self.client.post(
			reverse("logout"),
			REMOTE_ADDR="127.0.0.66",
			HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/117.0",
		)

		self.assertRedirects(response, reverse("home"))
		self.assertNotEqual(pre_logout_session_key, self.client.session.session_key)
		audit = LoginAttemptLog.objects.filter(username=self.user.username, failure_reason="logout").first()
		self.assertIsNotNone(audit)
		self.assertEqual(audit.ip_address, "127.0.0.66")
		self.assertNotEqual(audit.browser, "")
		self.assertNotEqual(audit.operating_system, "")

	def test_forced_logout_creates_login_attempt_log_entry(self):
		self.client.force_login(self.user)
		self.client.logout()

		self.assertTrue(
			LoginAttemptLog.objects.filter(
				user=self.user,
				username=self.user.username,
				failure_reason="forced_logout",
				role_key="logout",
			).exists()
		)

	def test_unlock_action_creates_audit_log_entry(self):
		staff = User.objects.create_user(
			username="unlock-staff",
			password="StrongPass123",
			is_staff=True,
		)
		staff.user_permissions.add(Permission.objects.get(codename="view_loginsecurity"))
		staff.user_permissions.add(Permission.objects.get(codename="change_loginsecurity"))
		staff.user_permissions.add(Permission.objects.get(codename="unlock_loginsecurity"))

		security = LoginSecurity.objects.create(user=self.user, failed_login_attempts=6, is_locked=True)
		self.client.force_login(staff)

		response = self.client.post(
			reverse("admin:accounts_loginsecurity_changelist"),
			data={"action": "unlock_accounts", "_selected_action": [str(security.pk)]},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		audit = LoginAttemptLog.objects.filter(
			user=self.user,
			username=self.user.username,
			failure_reason="account_unlocked",
			role_key="admin_action",
		).first()
		self.assertIsNotNone(audit)
		self.assertTrue(audit.is_unlock_event)
		self.assertEqual(audit.unlocked_by, staff)
		self.assertEqual(audit.unlock_reason, "Admin action: unlock selected accounts")


class SecurityConfigurationTests(CleanTestCase):
	def test_cookie_security_settings_enabled(self):
		from django.conf import settings

		self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
		self.assertIn(settings.SESSION_COOKIE_SAMESITE, {"Lax", "Strict", "None"})
		self.assertIn(settings.CSRF_COOKIE_SAMESITE, {"Lax", "Strict", "None"})
		self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)

	def test_security_middleware_enabled(self):
		from django.conf import settings

		self.assertIn("django.middleware.security.SecurityMiddleware", settings.MIDDLEWARE)

	def test_secure_cookie_flags_follow_debug_mode(self):
		from django.conf import settings

		self.assertIsInstance(settings.SESSION_COOKIE_SECURE, bool)
		self.assertIsInstance(settings.CSRF_COOKIE_SECURE, bool)

	def test_ssl_redirect_follows_debug_mode(self):
		from django.conf import settings

		self.assertIsInstance(settings.SECURE_SSL_REDIRECT, bool)

	def test_security_headers_present_on_login_page(self):
		response = self.client.get(reverse("administrator_login"))

		self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
		self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
		self.assertIsNotNone(response.headers.get("Referrer-Policy"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentLoginAttemptTests(CleanTransactionTestCase):
	reset_sequences = True

	def setUp(self):
		self.user = User.objects.create_user(username="concurrent-user", password="StrongPass123")
		AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)

	def _failed_attempt(self, ip_suffix):
		request = HttpRequest()
		request.META = {
			"REMOTE_ADDR": "127.0.9.200",
			"HTTP_USER_AGENT": "ConcurrentTest/1.0",
		}
		_register_failed_login(
			request,
			username=self.user.username,
			role_key="administrator",
			user=self.user,
			failure_reason="invalid_credentials",
		)

	def test_concurrent_failed_attempts_update_security_state(self):
		error_count = 0
		with ThreadPoolExecutor(max_workers=4) as executor:
			futures = [executor.submit(self._failed_attempt, idx + 1) for idx in range(4)]
			for future in futures:
				try:
					future.result(timeout=10)
				except Exception:
					error_count += 1

		security = LoginSecurity.objects.get(user=self.user)
		self.assertGreaterEqual(security.failed_login_attempts, 1)
		self.assertLess(error_count, 4)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EndToEndRoleWorkflowTests(CleanTestCase):
	def setUp(self):
		self.password = "StrongPass123"

		self.admin_user = User.objects.create_user(username="e2e-admin", password=self.password)
		self.teacher_user = User.objects.create_user(username="e2e-teacher", password=self.password)
		self.student_user = User.objects.create_user(username="e2e-student", password=self.password)
		self.parent_user = User.objects.create_user(username="e2e-parent", password=self.password)

		self.admin_profile = AccountProfile.objects.create(
			user=self.admin_user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.parent_profile = AccountProfile.objects.create(
			user=self.parent_user,
			role=AccountProfile.Role.PARENT,
			status=AccountProfile.Status.ACTIVE,
		)

		admin_group, _ = Group.objects.get_or_create(name="Administrator")
		teacher_group, _ = Group.objects.get_or_create(name="Teacher")
		student_group, _ = Group.objects.get_or_create(name="Student")
		parent_group, _ = Group.objects.get_or_create(name="Parent")

		self.admin_user.groups.add(admin_group)
		self.teacher_user.groups.add(teacher_group)
		self.student_user.groups.add(student_group)
		self.parent_user.groups.add(parent_group)

		self.admin_user.user_permissions.add(Permission.objects.get(codename="view_accountprofile"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_teacher"))
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_student"))

		portal_admin, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		portal_teacher, _ = CustomPermission.objects.get_or_create(
			code="access.portal.teacher",
			defaults={"name": "Access Teacher Portal", "is_active": True},
		)
		portal_student, _ = CustomPermission.objects.get_or_create(
			code="access.portal.student",
			defaults={"name": "Access Student Portal", "is_active": True},
		)
		portal_parent, _ = CustomPermission.objects.get_or_create(
			code="access.portal.parent",
			defaults={"name": "Access Parent Portal", "is_active": True},
		)

		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=portal_admin,
			defaults={"is_granted": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.TEACHER,
			permission=portal_teacher,
			defaults={"is_granted": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.STUDENT,
			permission=portal_student,
			defaults={"is_granted": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.PARENT,
			permission=portal_parent,
			defaults={"is_granted": True},
		)

		self.teacher = Teacher.objects.create(
			account=self.teacher_profile,
			employee_code="TCH-E2E-001",
			specialization="Science",
			status=Teacher.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=self.student_profile,
			student_code="STU-E2E-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		self.course = Course.objects.create(
			code="CRS-E2E-001",
			title="Integrated Science",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)
		Enrollment.objects.create(
			student=self.student,
			course=self.course,
			status=Enrollment.Status.ACTIVE,
			progress_percent=35,
		)

		self.exam = Exam.objects.create(
			title="E2E Exam",
			description="Role dashboard integration exam",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			total_marks=20,
			passing_marks=10,
		)
		StudentExam.objects.create(
			exam=self.exam,
			student=self.student,
			status=StudentExam.Status.GRADED,
			score="16.00",
			percentage="80.00",
			result_status=StudentExam.ResultStatus.PASSED,
		)

		self.plan = SubscriptionPlan.objects.create(
			name="E2E Monthly",
			description="Integration test plan",
			duration_days=30,
			price="15000.00",
			status=SubscriptionPlan.Status.ACTIVE,
		)
		self.subscription = StudentSubscription.objects.create(
			student=self.student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=timezone.now() + timedelta(days=30),
		)

		Payment.objects.create(
			student=self.student,
			requested_by=self.student_user,
			subscription=self.subscription,
			amount="15000.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-E2E-001",
		)

		Notification.objects.create(
			title="Admin Alert",
			message="Action required",
			recipient_type=Notification.RecipientType.ADMIN,
			admin_user=self.admin_user,
		)
		Notification.objects.create(
			title="Teacher Alert",
			message="Class updated",
			recipient_type=Notification.RecipientType.TEACHER,
			teacher=self.teacher,
		)
		Notification.objects.create(
			title="Student Alert",
			message="Homework posted",
			recipient_type=Notification.RecipientType.STUDENT,
			student=self.student,
		)
		Notification.objects.create(
			title="System Notice",
			message="Platform update",
			recipient_type=Notification.RecipientType.SYSTEM,
		)

	def _login(self, url_name, username):
		response = self.client.post(
			reverse(url_name),
			data={"username": username, "password": self.password},
		)
		self.assertEqual(response.status_code, 302)
		return response

	def test_administrator_daily_dashboard_flow(self):
		response = self._login("administrator_login", self.admin_user.username)
		self.assertEqual(response.url, reverse("admin_dashboard"))

		dashboard_response = self.client.get(reverse("admin_dashboard"))
		self.assertEqual(dashboard_response.status_code, 200)
		self.assertEqual(dashboard_response.context["total_students"], 1)
		self.assertEqual(dashboard_response.context["total_teachers"], 1)
		self.assertEqual(len(dashboard_response.context["pending_payments"]), 1)
		self.assertEqual(dashboard_response.context["total_exams"], 1)
		self.assertEqual(dashboard_response.context["graded_exam_attempts"], 1)

	def test_teacher_daily_workflow_shows_courses_and_students(self):
		response = self._login("teacher_login", self.teacher_user.username)
		self.assertEqual(response.url, reverse("teacher_dashboard"))

		dashboard_response = self.client.get(reverse("teacher_dashboard"))
		self.assertEqual(dashboard_response.status_code, 200)
		self.assertEqual(dashboard_response.context["total_courses"], 1)
		self.assertEqual(dashboard_response.context["total_students"], 1)
		self.assertEqual(dashboard_response.context["total_exams"], 1)
		self.assertEqual(dashboard_response.context["graded_exam_attempts"], 1)

	def test_student_daily_workflow_includes_subscription_and_payment_request(self):
		response = self._login("student_login", self.student_user.username)
		self.assertEqual(response.url, reverse("student_dashboard"))

		dashboard_response = self.client.get(reverse("student_dashboard"))
		self.assertEqual(dashboard_response.status_code, 200)
		self.assertEqual(dashboard_response.context["total_courses"], 1)
		self.assertEqual(dashboard_response.context["active_subscriptions_count"], 1)
		self.assertEqual(dashboard_response.context["available_exam_count"], 1)
		self.assertEqual(dashboard_response.context["graded_exam_count"], 1)

		payment_request_response = self.client.post(
			reverse("payments:payment_request"),
			data={
				"amount": "25000.00",
				"currency": "SYP",
				"method": Payment.Method.CASH,
				"transaction_reference": "",
				"notes": "E2E payment request",
			},
		)
		self.assertEqual(payment_request_response.status_code, 302)
		self.assertTrue(
			Payment.objects.filter(
				student=self.student,
				requested_by=self.student_user,
				status=Payment.Status.PENDING,
			).count() >= 2
		)

	def test_student_global_search_is_limited_to_owned_records(self):
		other_user = User.objects.create_user(username="e2e-student-2", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-E2E-002",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		Payment.objects.create(
			student=other_student,
			requested_by=other_user,
			amount="9999.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-E2E-OTHER",
		)

		response = self._login("student_login", self.student_user.username)
		self.assertEqual(response.url, reverse("student_dashboard"))

		search_response = self.client.get(reverse("dashboard:global_search"), {"q": "PAY-E2E-OTHER"})
		self.assertEqual(search_response.status_code, 200)
		self.assertEqual(search_response.context["payments_count"], 0)
		self.assertEqual(search_response.context["students_count"], 0)

	def test_parent_daily_workflow_and_global_search_access(self):
		response = self._login("parent_login", self.parent_user.username)
		self.assertEqual(response.url, reverse("parent_dashboard"))

		dashboard_response = self.client.get(reverse("parent_dashboard"))
		self.assertEqual(dashboard_response.status_code, 200)
		self.assertEqual(dashboard_response.context["total_students"], 1)
		self.assertEqual(dashboard_response.context["total_teachers"], 1)

		search_response = self.client.get(reverse("dashboard:global_search"), {"q": "CRS-E2E-001"})
		self.assertEqual(search_response.status_code, 200)
		self.assertEqual(search_response.context["students_count"], 0)
		self.assertEqual(search_response.context["payments_count"], 0)
		self.assertEqual(search_response.context["courses_count"], 1)
