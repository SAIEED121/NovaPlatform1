from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from notifications.forms import NotificationForm
from notifications.models import Notification
from students.models import Student
from teachers.models import Teacher


class NotificationTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.admin_user = User.objects.create_user(
			username="notify-admin",
			password=self.password,
			email="notify-admin@example.com",
		)
		self.unprivileged_user = User.objects.create_user(
			username="notify-user",
			password=self.password,
			email="notify-user@example.com",
		)
		self.student_user = User.objects.create_user(
			username="notify-student",
			password=self.password,
			email="notify-student@example.com",
		)
		self.teacher_user = User.objects.create_user(
			username="notify-teacher",
			password=self.password,
			email="notify-teacher@example.com",
		)
		AccountProfile.objects.create(
			user=self.admin_user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-NOTIFY-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-NOTIFY-001",
			specialization="Mathematics",
			status=Teacher.Status.ACTIVE,
		)

		self.notification = Notification.objects.create(
			title="Admin notice",
			message="Admin message",
			channel=Notification.Channel.IN_APP,
			recipient_type=Notification.RecipientType.ADMIN,
			admin_user=self.admin_user,
			status=Notification.Status.UNREAD,
		)
		self.student_notification = Notification.objects.create(
			title="Student notice",
			message="Student message",
			channel=Notification.Channel.IN_APP,
			recipient_type=Notification.RecipientType.STUDENT,
			student=self.student,
			status=Notification.Status.UNREAD,
		)
		self.teacher_notification = Notification.objects.create(
			title="Teacher notice",
			message="Teacher message",
			channel=Notification.Channel.IN_APP,
			recipient_type=Notification.RecipientType.TEACHER,
			teacher=self.teacher,
			status=Notification.Status.UNREAD,
		)

	def test_notification_form_requires_admin_recipient(self):
		form = NotificationForm(
			data={
				"title": "Test",
				"message": "Body",
				"channel": Notification.Channel.IN_APP,
				"recipient_type": Notification.RecipientType.ADMIN,
				"status": Notification.Status.UNREAD,
				"sent_at": "2026-01-01T10:00",
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("admin_user", form.errors)

	def test_notification_list_requires_permission(self):
		self.client.force_login(self.unprivileged_user)
		response = self.client.get(reverse("notifications:notification_list"))
		self.assertIn(response.status_code, (302, 403))

	def test_notification_list_with_permission(self):
		self.admin_user.user_permissions.add(Permission.objects.get(codename="view_notification"))
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("notifications:notification_list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Admin notice")

	def test_inbox_returns_user_notifications(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("notifications:inbox"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Admin notice")

	def test_mark_read_changes_notification_status(self):
		self.client.force_login(self.admin_user)
		response = self.client.post(reverse("notifications:mark_read", kwargs={"pk": self.notification.pk}))
		self.assertEqual(response.status_code, 302)
		self.notification.refresh_from_db()
		self.assertEqual(self.notification.status, Notification.Status.READ)

	def test_student_notification_views_are_scoped_to_owned_records(self):
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_notification"))
		self.client.force_login(self.student_user)

		list_response = self.client.get(reverse("notifications:notification_list"))
		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, "Student notice")
		self.assertNotContains(list_response, "Admin notice")

		detail_response = self.client.get(reverse("notifications:notification_detail", args=[self.notification.pk]))
		self.assertEqual(detail_response.status_code, 404)

	def test_teacher_notification_views_are_scoped_to_owned_records(self):
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_notification"))
		self.client.force_login(self.teacher_user)

		list_response = self.client.get(reverse("notifications:notification_list"))
		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, "Teacher notice")
		self.assertNotContains(list_response, "Admin notice")
		self.assertNotContains(list_response, "Student notice")

	def test_teacher_cannot_update_admin_notification(self):
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="change_notification"))
		self.client.force_login(self.teacher_user)

		response = self.client.post(
			reverse("notifications:notification_update", args=[self.notification.pk]),
			data={
				"title": "Tampered",
				"message": self.notification.message,
				"channel": self.notification.channel,
				"recipient_type": self.notification.recipient_type,
				"admin_user": self.admin_user.pk,
				"student": "",
				"teacher": "",
				"status": self.notification.status,
				"sent_at": timezone.localtime(self.notification.sent_at).strftime("%Y-%m-%dT%H:%M"),
			},
		)
		self.assertEqual(response.status_code, 404)
