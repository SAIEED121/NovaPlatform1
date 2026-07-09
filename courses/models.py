from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator
from django.utils import timezone
from novaplatform_backend.upload_security import homework_upload_to, validate_homework_attachment
from novaplatform_backend.academic_subjects import branch_validation_error


class Category(models.Model):
	name = models.CharField(max_length=120, unique=True)
	description = models.TextField(blank=True)
	status = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]
		indexes = [
			models.Index(fields=["name"]),
		]

	def __str__(self):
		return self.name


class Course(models.Model):
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
		DRAFT = "draft", "Draft"
		PUBLISHED = "published", "Published"
		ARCHIVED = "archived", "Archived"

	code = models.CharField(max_length=32, unique=True)
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	category = models.ForeignKey(
		"courses.Category",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="courses",
	)
	teacher = models.ForeignKey(
		"teachers.Teacher",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="courses",
	)
	grade_level = models.CharField(max_length=32, choices=GradeLevel.choices)
	branch = models.CharField(max_length=20, choices=Branch.choices, default=Branch.GENERAL)
	price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	start_date = models.DateField(null=True, blank=True)
	end_date = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["code"]
		indexes = [
			models.Index(fields=["code"]),
			models.Index(fields=["status"]),
			models.Index(fields=["grade_level", "branch"]),
		]

	def clean(self):
		error = branch_validation_error(self.grade_level, self.branch)
		if error:
			raise ValidationError({"branch": error})

	def __str__(self):
		return f"{self.code} - {self.title}"


class Enrollment(models.Model):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		COMPLETED = "completed", "Completed"
		DROPPED = "dropped", "Dropped"
		SUSPENDED = "suspended", "Suspended"

	student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="enrollments")
	course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="enrollments")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	progress_percent = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
	enrolled_at = models.DateTimeField(auto_now_add=True)
	completed_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-enrolled_at"]
		unique_together = ("student", "course")
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["student", "course"]),
		]

	def __str__(self):
		return f"{self.student.student_code} -> {self.course.code}"


class Lesson(models.Model):
	course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="lessons")
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	order = models.PositiveIntegerField(default=1)
	duration_minutes = models.PositiveIntegerField(default=0)
	video_url = models.URLField(blank=True)
	is_published = models.BooleanField(default=False)
	due_date = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["course", "order", "title"]
		unique_together = ("course", "order")
		indexes = [
			models.Index(fields=["course", "order"]),
			models.Index(fields=["is_published"]),
		]

	def __str__(self):
		return f"{self.course.code} - {self.order} - {self.title}"


class Schedule(models.Model):
	course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="schedules")
	lesson = models.ForeignKey(
		"courses.Lesson",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="schedules",
	)
	title = models.CharField(max_length=200)
	starts_at = models.DateTimeField()
	ends_at = models.DateTimeField()
	meeting_url = models.URLField(blank=True)
	is_live = models.BooleanField(default=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-starts_at"]
		indexes = [
			models.Index(fields=["course", "starts_at"]),
			models.Index(fields=["is_live"]),
		]

	def __str__(self):
		return f"{self.course.code} - {self.title}"


class HomeworkSubmission(models.Model):
	class Status(models.TextChoices):
		SUBMITTED = "submitted", "Submitted"
		REVIEWED = "reviewed", "Reviewed"
		REJECTED = "rejected", "Rejected"

	enrollment = models.ForeignKey(
		"courses.Enrollment",
		on_delete=models.CASCADE,
		related_name="homework_submissions",
	)
	lesson = models.ForeignKey(
		"courses.Lesson",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="homework_submissions",
	)
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	attachment = models.FileField(upload_to=homework_upload_to, validators=[validate_homework_attachment])
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
	grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	feedback = models.TextField(blank=True)
	submitted_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-submitted_at"]
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["enrollment", "submitted_at"]),
		]

	def __str__(self):
		return f"{self.enrollment.student.student_code} - {self.title}"

	def save(self, *args, **kwargs):
		if self.status == self.Status.REVIEWED and not self.reviewed_at:
			self.reviewed_at = timezone.now()
		if self.status != self.Status.REVIEWED and self.reviewed_at:
			self.reviewed_at = None
		super().save(*args, **kwargs)
