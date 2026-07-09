from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q


class NotificationQuerySet(models.QuerySet):
	def for_user(self, user):
		if not user or not user.is_authenticated:
			return self.none()

		# Use a single SQL filter path by joining through related profiles.
		return self.filter(
			Q(recipient_type=Notification.RecipientType.SYSTEM)
			| Q(recipient_type=Notification.RecipientType.ADMIN, admin_user_id=user.id)
			| Q(recipient_type=Notification.RecipientType.STUDENT, student__account__user_id=user.id)
			| Q(recipient_type=Notification.RecipientType.TEACHER, teacher__account__user_id=user.id)
		)

	def unread_for_user(self, user):
		return self.for_user(user).filter(status=Notification.Status.UNREAD)


class NotificationManager(models.Manager):
	def get_queryset(self):
		return NotificationQuerySet(self.model, using=self._db)

	def for_user(self, user):
		return self.get_queryset().for_user(user)

	def unread_for_user(self, user):
		return self.get_queryset().unread_for_user(user)

	def unread_count_for_user(self, user):
		return self.unread_for_user(user).count()


class Notification(models.Model):
	class Channel(models.TextChoices):
		IN_APP = "in_app", "In App"
		EMAIL = "email", "Email"
		SMS = "sms", "SMS"
		PUSH = "push", "Push"

	class RecipientType(models.TextChoices):
		ADMIN = "admin", "Admin"
		STUDENT = "student", "Student"
		TEACHER = "teacher", "Teacher"
		SYSTEM = "system", "System"

	class Status(models.TextChoices):
		UNREAD = "unread", "Unread"
		READ = "read", "Read"
		FAILED = "failed", "Failed"

	title = models.CharField(max_length=200)
	message = models.TextField()
	channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
	recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)
	student = models.ForeignKey(
		"students.Student",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="notifications",
	)
	teacher = models.ForeignKey(
		"teachers.Teacher",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="notifications",
	)
	admin_user = models.ForeignKey(
		"auth.User",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="admin_notifications",
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNREAD)
	sent_at = models.DateTimeField(default=timezone.now)
	read_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	objects = NotificationManager()

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["recipient_type", "status"]),
			models.Index(fields=["admin_user"]),
			models.Index(fields=["sent_at"]),
		]

	def clean(self):
		if self.recipient_type == self.RecipientType.ADMIN and not self.admin_user:
			raise ValidationError("Admin notification requires an admin user recipient.")
		if self.recipient_type == self.RecipientType.STUDENT and not self.student:
			raise ValidationError("Student notification requires a student recipient.")
		if self.recipient_type == self.RecipientType.TEACHER and not self.teacher:
			raise ValidationError("Teacher notification requires a teacher recipient.")
		if self.recipient_type == self.RecipientType.SYSTEM and (
			self.student_id or self.teacher_id or self.admin_user_id
		):
			raise ValidationError("System notifications should not target a specific student or teacher.")

		if self.recipient_type != self.RecipientType.ADMIN:
			self.admin_user = None
		if self.recipient_type != self.RecipientType.STUDENT:
			self.student = None
		if self.recipient_type != self.RecipientType.TEACHER:
			self.teacher = None

	def mark_as_read(self):
		if self.status == self.Status.UNREAD:
			self.status = self.Status.READ
			self.read_at = timezone.now()
			self.save(update_fields=["status", "read_at", "updated_at"])

	def __str__(self):
		return f"{self.title} ({self.recipient_type})"
