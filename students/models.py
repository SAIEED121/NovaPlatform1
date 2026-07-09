from django.core.exceptions import ValidationError
from django.db import models

from novaplatform_backend.academic_subjects import branch_validation_error


class Student(models.Model):
	class GradeLevel(models.TextChoices):
		FIRST_PRIMARY = "grade_1_primary", "Grade 1 Primary"
		SECOND_PRIMARY = "grade_2_primary", "Grade 2 Primary"
		THIRD_PRIMARY = "grade_3_primary", "Grade 3 Primary"
		FOURTH_PRIMARY = "grade_4_primary", "Grade 4 Primary"
		FIFTH_PRIMARY = "grade_5_primary", "Grade 5 Primary"
		SIXTH_PRIMARY = "grade_6_primary", "Grade 6 Primary"
		FIRST_PREPARATORY = "grade_1_preparatory", "Grade 1 Preparatory"
		SECOND_PREPARATORY = "grade_2_preparatory", "Grade 2 Preparatory"
		THIRD_PREPARATORY = "grade_3_preparatory", "Grade 3 Preparatory"
		FIRST_SECONDARY = "grade_1_secondary", "Grade 1 Secondary"
		SECOND_SECONDARY = "grade_2_secondary", "Grade 2 Secondary"
		THIRD_SECONDARY = "grade_3_secondary", "Grade 3 Secondary"

	class Branch(models.TextChoices):
		GENERAL = "general", "General"
		SCIENCE = "science", "Science"
		LITERARY = "literary", "Literary"

	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INACTIVE = "inactive", "Inactive"
		GRADUATED = "graduated", "Graduated"
		BLOCKED = "blocked", "Blocked"

	account = models.OneToOneField(
		"accounts.AccountProfile",
		on_delete=models.CASCADE,
		related_name="student_profile",
	)
	student_code = models.CharField(max_length=32, unique=True)
	grade_level = models.CharField(max_length=32, choices=GradeLevel.choices)
	branch = models.CharField(max_length=20, choices=Branch.choices, default=Branch.GENERAL)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	date_of_birth = models.DateField(null=True, blank=True)
	guardian_name = models.CharField(max_length=150, blank=True)
	guardian_phone = models.CharField(max_length=20, blank=True)
	joined_at = models.DateField(auto_now_add=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["student_code"]
		indexes = [
			models.Index(fields=["student_code"]),
			models.Index(fields=["status"]),
			models.Index(fields=["grade_level", "branch"]),
		]

	def clean(self):
		error = branch_validation_error(self.grade_level, self.branch)
		if error:
			raise ValidationError({"branch": error})

	def __str__(self):
		return f"{self.student_code} - {self.account.user.get_full_name() or self.account.user.username}"
