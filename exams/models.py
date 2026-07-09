from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from decimal import Decimal


class Exam(models.Model):
	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		PUBLISHED = "published", "Published"
		ARCHIVED = "archived", "Archived"

	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	teacher = models.ForeignKey("teachers.Teacher", on_delete=models.CASCADE, related_name="exams")
	course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="exams")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	start_at = models.DateTimeField(null=True, blank=True)
	end_at = models.DateTimeField(null=True, blank=True)
	duration_minutes = models.PositiveIntegerField(default=60)
	total_marks = models.DecimalField(max_digits=7, decimal_places=2, default=0)
	passing_marks = models.DecimalField(max_digits=7, decimal_places=2, default=0)
	allow_late_submission = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		permissions = [
			("publish_exam", "Can publish exam"),
			("unpublish_exam", "Can unpublish exam"),
		]
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["teacher", "course"]),
			models.Index(fields=["start_at", "end_at"]),
		]

	def clean(self):
		if self.start_at and self.end_at and self.end_at <= self.start_at:
			raise ValidationError({"end_at": "End time must be after start time."})
		if self.passing_marks > self.total_marks:
			raise ValidationError({"passing_marks": "Passing marks cannot exceed total marks."})
		if self.course_id and self.teacher_id and self.course.teacher_id != self.teacher_id:
			raise ValidationError({"course": "Exam course must belong to the exam owner teacher."})

	def __str__(self):
		return self.title

	def is_available_to_students(self, at=None):
		moment = at or timezone.now()
		if self.status != self.Status.PUBLISHED:
			return False
		if self.start_at and moment < self.start_at:
			return False
		if self.end_at and moment > self.end_at:
			return False
		return True

	def availability_state(self, at=None):
		moment = at or timezone.now()
		if self.status != self.Status.PUBLISHED:
			return "unpublished"
		if self.start_at and moment < self.start_at:
			return "upcoming"
		if self.end_at and moment > self.end_at:
			return "closed"
		return "open"


class Question(models.Model):
	class QuestionType(models.TextChoices):
		MCQ = "mcq", "MCQ"
		TRUE_FALSE = "true_false", "True/False"
		ESSAY = "essay", "Essay"

	exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="questions")
	text = models.TextField()
	question_type = models.CharField(max_length=20, choices=QuestionType.choices)
	marks = models.DecimalField(max_digits=6, decimal_places=2, default=1)
	display_order = models.PositiveIntegerField(default=1)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["exam", "display_order", "id"]
		constraints = [
			models.UniqueConstraint(fields=["exam", "display_order"], name="exams_question_exam_order_unique"),
		]
		indexes = [
			models.Index(fields=["exam", "question_type"]),
		]

	def __str__(self):
		return f"{self.exam_id}:{self.display_order}"


class Choice(models.Model):
	question = models.ForeignKey("exams.Question", on_delete=models.CASCADE, related_name="choices")
	text = models.CharField(max_length=500)
	is_correct = models.BooleanField(default=False)
	display_order = models.PositiveIntegerField(default=1)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["question", "display_order", "id"]
		constraints = [
			models.UniqueConstraint(fields=["question", "display_order"], name="exams_choice_question_order_unique"),
		]
		indexes = [
			models.Index(fields=["question", "is_correct"]),
		]

	def clean(self):
		if not self.question_id:
			return
		if self.question.question_type == Question.QuestionType.ESSAY:
			raise ValidationError({"question": "Essay questions cannot have choices."})

	def __str__(self):
		return self.text


class StudentExam(models.Model):
	class Status(models.TextChoices):
		ASSIGNED = "assigned", "Assigned"
		STARTED = "started", "Started"
		SUBMITTED = "submitted", "Submitted"
		GRADED = "graded", "Graded"

	class ResultStatus(models.TextChoices):
		PENDING = "pending", "Pending"
		PASSED = "passed", "Passed"
		FAILED = "failed", "Failed"

	exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="student_exams")
	student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="student_exams")
	attempt_no = models.PositiveIntegerField(default=1)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ASSIGNED)
	started_at = models.DateTimeField(null=True, blank=True)
	submitted_at = models.DateTimeField(null=True, blank=True)
	graded_at = models.DateTimeField(null=True, blank=True)
	score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
	percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
	result_status = models.CharField(max_length=20, choices=ResultStatus.choices, default=ResultStatus.PENDING)
	grader_notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(fields=["exam", "student", "attempt_no"], name="exams_studentexam_unique_attempt"),
		]
		indexes = [
			models.Index(fields=["exam", "student"]),
			models.Index(fields=["status"]),
		]

	def clean(self):
		if self.started_at and self.submitted_at and self.submitted_at < self.started_at:
			raise ValidationError({"submitted_at": "Submission time cannot be before start time."})
		if self.score is not None and self.score < 0:
			raise ValidationError({"score": "Score cannot be negative."})
		if self.percentage is not None and self.percentage < 0:
			raise ValidationError({"percentage": "Percentage cannot be negative."})

	def recalculate_result(self):
		answers = self.answers.select_related("question")
		total_score = Decimal("0")
		pending_essay = False
		for answer in answers:
			if answer.question.question_type == Question.QuestionType.ESSAY and answer.score is None:
				pending_essay = True
			if answer.score is not None:
				total_score += answer.score

		total_marks = self.exam.total_marks or Decimal("0")
		if total_marks > 0:
			self.percentage = (total_score * Decimal("100") / total_marks).quantize(Decimal("0.01"))
		else:
			self.percentage = Decimal("0.00")

		self.score = total_score
		if pending_essay:
			self.result_status = self.ResultStatus.PENDING
			if self.submitted_at:
				self.status = self.Status.SUBMITTED
			self.graded_at = None
		else:
			self.result_status = (
				self.ResultStatus.PASSED if total_score >= self.exam.passing_marks else self.ResultStatus.FAILED
			)
			self.status = self.Status.GRADED
			self.graded_at = timezone.now()

		self.save(update_fields=["status", "score", "percentage", "result_status", "graded_at", "updated_at"])

	def __str__(self):
		return f"{self.exam_id}:{self.student_id}:{self.attempt_no}"


class StudentAnswer(models.Model):
	student_exam = models.ForeignKey("exams.StudentExam", on_delete=models.CASCADE, related_name="answers")
	question = models.ForeignKey("exams.Question", on_delete=models.CASCADE, related_name="student_answers")
	selected_choice = models.ForeignKey(
		"exams.Choice",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="student_answers",
	)
	answer_text = models.TextField(blank=True)
	is_correct = models.BooleanField(null=True, blank=True)
	score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
	answered_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["student_exam", "question_id"]
		constraints = [
			models.UniqueConstraint(fields=["student_exam", "question"], name="exams_studentanswer_unique_per_question"),
		]
		indexes = [
			models.Index(fields=["student_exam", "question"]),
		]

	def clean(self):
		if self.student_exam.exam_id != self.question.exam_id:
			raise ValidationError({"question": "Question must belong to the same exam."})

		if self.selected_choice and self.selected_choice.question_id != self.question_id:
			raise ValidationError({"selected_choice": "Selected choice must belong to the same question."})

		if self.question.question_type == Question.QuestionType.ESSAY:
			if self.selected_choice_id:
				raise ValidationError({"selected_choice": "Essay answers cannot use selected choices."})
			if not self.answer_text.strip():
				raise ValidationError({"answer_text": "Essay answers require answer text."})
		else:
			if not self.selected_choice_id:
				raise ValidationError({"selected_choice": "A choice is required for MCQ/True-False answers."})

		if self.score is not None and self.score < 0:
			raise ValidationError({"score": "Score cannot be negative."})

	def __str__(self):
		return f"{self.student_exam_id}:{self.question_id}"
