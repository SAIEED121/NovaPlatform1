from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from novaplatform_backend.upload_security import profile_photo_upload_to, validate_profile_photo


class AccountProfile(models.Model):
	class Role(models.TextChoices):
		ADMIN = "admin", "Admin"
		TEACHER = "teacher", "Teacher"
		STUDENT = "student", "Student"
		PARENT = "parent", "Parent"

	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		PENDING = "pending", "Pending"
		SUSPENDED = "suspended", "Suspended"
		ARCHIVED = "archived", "Archived"

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="account_profile",
	)
	role = models.CharField(max_length=20, choices=Role.choices)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	phone_number = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=100, blank=True)
	profile_photo = models.ImageField(
		upload_to=profile_photo_upload_to,
		blank=True,
		null=True,
		validators=[validate_profile_photo],
	)
	last_seen_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["role"]),
			models.Index(fields=["status"]),
		]

	def __str__(self):
		return f"{self.user.username} ({self.role})"


class CustomPermission(models.Model):
	code = models.CharField(max_length=120, unique=True)
	name = models.CharField(max_length=160)
	description = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["code"]
		indexes = [
			models.Index(fields=["code"]),
			models.Index(fields=["is_active"]),
		]

	def __str__(self):
		return self.code


class RoleCustomPermission(models.Model):
	role = models.CharField(max_length=20, choices=AccountProfile.Role.choices)
	permission = models.ForeignKey(
		"accounts.CustomPermission",
		on_delete=models.CASCADE,
		related_name="role_assignments",
	)
	is_granted = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["role", "permission__code"]
		unique_together = ("role", "permission")
		indexes = [
			models.Index(fields=["role", "permission"]),
		]

	def __str__(self):
		state = "grant" if self.is_granted else "deny"
		return f"{self.role}:{self.permission.code} ({state})"


class UserCustomPermission(models.Model):
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="custom_permissions",
	)
	permission = models.ForeignKey(
		"accounts.CustomPermission",
		on_delete=models.CASCADE,
		related_name="user_assignments",
	)
	is_granted = models.BooleanField(default=True)
	notes = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["user__username", "permission__code"]
		unique_together = ("user", "permission")
		indexes = [
			models.Index(fields=["user", "permission"]),
		]

	def __str__(self):
		state = "grant" if self.is_granted else "deny"
		return f"{self.user.username}:{self.permission.code} ({state})"


class ActivityLog(models.Model):
	class EventType(models.TextChoices):
		LOGIN = "login", "Login"
		EDIT = "edit", "Edit"
		DELETE = "delete", "Delete"
		PAYMENT = "payment", "Payment"

	actor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="activity_logs",
	)
	event_type = models.CharField(max_length=20, choices=EventType.choices)
	target_model = models.CharField(max_length=120)
	target_id = models.CharField(max_length=64, blank=True)
	action = models.CharField(max_length=80)
	description = models.TextField(blank=True)
	metadata = models.JSONField(default=dict, blank=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["event_type", "created_at"]),
			models.Index(fields=["target_model", "target_id"]),
		]

	def __str__(self):
		actor = self.actor.username if self.actor else "system"
		return f"{self.event_type}:{self.target_model}:{self.target_id} by {actor}"


class LoginSecurity(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="login_security",
	)
	failed_login_attempts = models.PositiveIntegerField(default=0)
	is_locked = models.BooleanField(default=False)
	locked_at = models.DateTimeField(null=True, blank=True)
	last_failed_login = models.DateTimeField(null=True, blank=True)
	last_successful_login = models.DateTimeField(null=True, blank=True)
	last_failed_ip = models.GenericIPAddressField(null=True, blank=True)
	last_successful_ip = models.GenericIPAddressField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		indexes = [
			models.Index(fields=["is_locked", "failed_login_attempts"]),
			models.Index(fields=["locked_at"]),
		]
		permissions = [
			("unlock_loginsecurity", "Can unlock locked accounts"),
		]

	def __str__(self):
		return f"{self.user.username} ({'locked' if self.is_locked else 'open'})"


class LoginAttemptLog(models.Model):
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="login_attempt_logs",
	)
	username = models.CharField(max_length=150)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.CharField(max_length=512, blank=True)
	browser = models.CharField(max_length=128, blank=True)
	operating_system = models.CharField(max_length=128, blank=True)
	attempted_at = models.DateTimeField(auto_now_add=True)
	is_successful = models.BooleanField(default=False)
	failure_reason = models.CharField(max_length=64, blank=True)
	role_key = models.CharField(max_length=32, blank=True)
	is_lock_event = models.BooleanField(default=False)
	is_unlock_event = models.BooleanField(default=False)
	unlocked_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="unlock_audit_logs",
	)
	unlock_reason = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ["-attempted_at"]
		indexes = [
			models.Index(fields=["username", "attempted_at"]),
			models.Index(fields=["is_successful", "attempted_at"]),
			models.Index(fields=["ip_address", "attempted_at"]),
		]

	def __str__(self):
		status = "success" if self.is_successful else "failed"
		return f"{self.username} {status} at {self.attempted_at:%Y-%m-%d %H:%M:%S}"

	def save(self, *args, **kwargs):
		if self.pk and type(self).objects.filter(pk=self.pk).exists():
			raise ValidationError("LoginAttemptLog records are immutable and cannot be edited.")
		return super().save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		raise ValidationError("LoginAttemptLog records are immutable and cannot be deleted.")


class LoginIPBlock(models.Model):
	ip_address = models.GenericIPAddressField(unique=True)
	failed_attempts = models.PositiveIntegerField(default=0)
	first_failed_at = models.DateTimeField(null=True, blank=True)
	last_failed_at = models.DateTimeField(null=True, blank=True)
	blocked_until = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		indexes = [
			models.Index(fields=["blocked_until"]),
			models.Index(fields=["last_failed_at"]),
		]

	def __str__(self):
		if self.blocked_until and self.blocked_until > timezone.now():
			return f"{self.ip_address} (blocked)"
		return f"{self.ip_address} (open)"


class SuspiciousActivity(models.Model):
	class EventType(models.TextChoices):
		ONE_IP_MULTIPLE_USERNAMES = "one_ip_multiple_usernames", "One IP Multiple Usernames"
		ONE_USERNAME_MULTIPLE_IPS = "one_username_multiple_ips", "One Username Multiple IPs"

	event_type = models.CharField(max_length=40, choices=EventType.choices)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	username = models.CharField(max_length=150, blank=True)
	window_seconds = models.PositiveIntegerField(default=900)
	threshold = models.PositiveIntegerField(default=0)
	observed_count = models.PositiveIntegerField(default=0)
	sample_count = models.PositiveIntegerField(default=1)
	details = models.JSONField(default=dict, blank=True)
	detected_at = models.DateTimeField(auto_now_add=True)
	last_seen_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-last_seen_at"]
		indexes = [
			models.Index(fields=["event_type", "last_seen_at"]),
			models.Index(fields=["ip_address", "last_seen_at"]),
			models.Index(fields=["username", "last_seen_at"]),
		]

	def __str__(self):
		subject = self.ip_address or self.username or "unknown"
		return f"{self.event_type}:{subject}"
