from django.db import models


class Teacher(models.Model):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		ON_LEAVE = "on_leave", "On Leave"
		INACTIVE = "inactive", "Inactive"

	account = models.OneToOneField(
		"accounts.AccountProfile",
		on_delete=models.CASCADE,
		related_name="teacher_profile",
	)
	employee_code = models.CharField(max_length=32, unique=True)
	specialization = models.CharField(max_length=150)
	bio = models.TextField(blank=True)
	years_of_experience = models.PositiveSmallIntegerField(default=0)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	hired_at = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["employee_code"]
		indexes = [
			models.Index(fields=["employee_code"]),
			models.Index(fields=["status"]),
			models.Index(fields=["specialization"]),
		]

	def __str__(self):
		return f"{self.employee_code} - {self.account.user.get_full_name() or self.account.user.username}"
