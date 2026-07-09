from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from students.models import Student
from subscriptions.forms import StudentSubscriptionForm
from subscriptions.models import StudentSubscription, SubscriptionPlan


class SubscriptionTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.admin_user = User.objects.create_user(username="sub-admin", password=self.password)
		self.student_user = User.objects.create_user(username="sub-student", password=self.password)

		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-SUB-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.plan = SubscriptionPlan.objects.create(
			name="Basic Plan",
			duration_days=30,
			price="50.00",
			status=SubscriptionPlan.Status.ACTIVE,
		)

		self.subscription = StudentSubscription.objects.create(
			student=self.student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now() - timedelta(days=2),
			ends_at=timezone.now() + timedelta(days=20),
		)

	def test_student_subscription_form_rejects_invalid_period(self):
		form = StudentSubscriptionForm(
			data={
				"student": self.student.pk,
				"plan": self.plan.pk,
				"status": StudentSubscription.Status.ACTIVE,
				"started_at": "2026-01-10T10:00",
				"ends_at": "2026-01-09T10:00",
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("ends_at", form.errors)

	def test_plan_list_requires_permission(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("subscriptions:plan_list"))
		self.assertIn(response.status_code, (302, 403))

	def test_plan_view_permission_can_be_granted(self):
		self.admin_user.user_permissions.add(Permission.objects.get(codename="view_subscriptionplan"))
		self.assertTrue(self.admin_user.has_perm("subscriptions.view_subscriptionplan"))

	def test_auto_expire_manager_updates_eligible_rows(self):
		expired_subscription = StudentSubscription.objects.create(
			student=self.student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now() - timedelta(days=40),
			ends_at=timezone.now() + timedelta(days=1),
		)
		StudentSubscription.objects.filter(pk=expired_subscription.pk).update(
			ends_at=timezone.now() - timedelta(days=1),
			status=StudentSubscription.Status.ACTIVE,
		)
		updated_count = StudentSubscription.objects.auto_expire()
		expired_subscription.refresh_from_db()
		self.assertGreaterEqual(updated_count, 1)
		self.assertEqual(expired_subscription.status, StudentSubscription.Status.EXPIRED)

	def test_apply_automatic_expiration_handles_missing_end_date(self):
		subscription = StudentSubscription(
			student=self.student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=None,
		)

		# Edge-case safety: avoid TypeError before model field validation runs.
		subscription.apply_automatic_expiration()
		self.assertEqual(subscription.status, StudentSubscription.Status.ACTIVE)

	def test_student_subscription_detail_requires_permission(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(
			reverse("subscriptions:student_subscription_detail", kwargs={"pk": self.subscription.pk})
		)
		self.assertIn(response.status_code, (302, 403))

	def test_student_subscription_views_are_scoped_to_own_records(self):
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_studentsubscription"))

		other_user = User.objects.create_user(username="sub-other", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-SUB-OTHER",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		other_subscription = StudentSubscription.objects.create(
			student=other_student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=timezone.now() + timedelta(days=15),
		)

		self.client.force_login(self.student_user)

		list_response = self.client.get(reverse("subscriptions:student_subscription_list"))
		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, self.student.student_code)
		self.assertNotContains(list_response, other_student.student_code)

		detail_response = self.client.get(
			reverse("subscriptions:student_subscription_detail", kwargs={"pk": other_subscription.pk})
		)
		self.assertEqual(detail_response.status_code, 404)

	def test_student_subscription_detail_renders_started_and_end_dates(self):
		staff_user = User.objects.create_user(username="sub-staff", password=self.password, is_staff=True)
		staff_user.user_permissions.add(Permission.objects.get(codename="view_studentsubscription"))
		self.client.force_login(staff_user)

		response = self.client.get(
			reverse("subscriptions:student_subscription_detail", kwargs={"pk": self.subscription.pk})
		)

		self.assertEqual(response.status_code, 200)
		started_display = timezone.localtime(self.subscription.started_at).strftime("%Y-%m-%d")
		ends_display = timezone.localtime(self.subscription.ends_at).strftime("%Y-%m-%d")
		self.assertContains(response, started_display)
		self.assertContains(response, ends_display)

	def test_non_student_with_view_permission_does_not_see_student_subscriptions(self):
		teacher_user = User.objects.create_user(username="sub-teacher", password=self.password)
		AccountProfile.objects.create(
			user=teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		teacher_user.user_permissions.add(Permission.objects.get(codename="view_studentsubscription"))

		self.client.force_login(teacher_user)
		response = self.client.get(reverse("subscriptions:student_subscription_list"))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, self.student.student_code)
