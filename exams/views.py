from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, DecimalField, FloatField, Q, Value
from django.db.models.functions import Coalesce
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ChoiceForm, EssayManualGradeForm, ExamForm, QuestionForm, StudentExamSubmissionForm
from .models import Choice, Exam, Question, StudentAnswer, StudentExam
from courses.models import Enrollment
from notifications.models import Notification
from students.models import Student


def _create_student_notifications(*, students, title, message):
	student_ids = list(students.values_list("id", flat=True).distinct())
	if not student_ids:
		return

	Notification.objects.bulk_create(
		[
			Notification(
				title=title,
				message=message,
				channel=Notification.Channel.IN_APP,
				recipient_type=Notification.RecipientType.STUDENT,
				student_id=student_id,
				status=Notification.Status.UNREAD,
			)
			for student_id in student_ids
		]
	)


def _create_admin_notifications(*, title, message):
	UserModel = get_user_model()
	admin_ids = list(
		UserModel.objects.filter(Q(is_superuser=True) | Q(groups__name="Administrator")).values_list("id", flat=True).distinct()
	)
	if not admin_ids:
		return

	Notification.objects.bulk_create(
		[
			Notification(
				title=title,
				message=message,
				channel=Notification.Channel.IN_APP,
				recipient_type=Notification.RecipientType.ADMIN,
				admin_user_id=admin_id,
				status=Notification.Status.UNREAD,
			)
			for admin_id in admin_ids
		]
	)


def _notify_new_exam_created(exam):
	Notification.objects.create(
		title="New exam created",
		message=f"A new exam '{exam.title}' was created for course {exam.course.code}.",
		channel=Notification.Channel.IN_APP,
		recipient_type=Notification.RecipientType.TEACHER,
		teacher=exam.teacher,
		status=Notification.Status.UNREAD,
	)
	_create_admin_notifications(
		title="New exam created",
		message=f"{exam.teacher.account.user.get_full_name() or exam.teacher.account.user.username} created exam '{exam.title}'.",
	)


def _notify_exam_published(exam):
	students = Student.objects.filter(enrollments__course=exam.course, enrollments__status=Enrollment.Status.ACTIVE).distinct()
	_create_student_notifications(
		students=students,
		title="Exam published",
		message=f"Exam '{exam.title}' is now published and available.",
	)


def _notify_exam_graded(student_exam):
	Notification.objects.create(
		title="Exam graded",
		message=f"Your exam '{student_exam.exam.title}' has been graded.",
		channel=Notification.Channel.IN_APP,
		recipient_type=Notification.RecipientType.STUDENT,
		student=student_exam.student,
		status=Notification.Status.UNREAD,
	)


class TeacherOwnedExamMixin(LoginRequiredMixin):
	def _get_teacher(self):
		profile = getattr(self.request.user, "account_profile", None)
		if profile is None:
			return None
		return getattr(profile, "teacher_profile", None)

	def _require_teacher(self):
		teacher = self._get_teacher()
		if teacher is None:
			raise PermissionDenied("Teacher profile is required.")
		return teacher

	def get_exam_queryset(self):
		teacher = self._require_teacher()
		return Exam.objects.filter(teacher=teacher).select_related("course", "teacher", "teacher__account", "teacher__account__user")

	def get_exam(self, exam_pk):
		return get_object_or_404(self.get_exam_queryset(), pk=exam_pk)


class StudentOwnedExamMixin(LoginRequiredMixin):
	permission_required = "exams.view_exam"

	def _get_student(self):
		profile = getattr(self.request.user, "account_profile", None)
		if profile is None:
			return None
		return getattr(profile, "student_profile", None)

	def _require_student(self):
		student = self._get_student()
		if student is None:
			raise PermissionDenied("Student profile is required.")
		return student

	def _student_exam_queryset(self):
		student = self._require_student()
		return Exam.objects.filter(
			status=Exam.Status.PUBLISHED,
			course__enrollments__student=student,
			course__enrollments__status=Enrollment.Status.ACTIVE,
		).distinct().select_related(
			"course",
			"teacher",
			"teacher__account",
			"teacher__account__user",
		)

	def get_student_exam(self, exam_pk):
		return get_object_or_404(self._student_exam_queryset(), pk=exam_pk)


class ExamListView(TeacherOwnedExamMixin, PermissionRequiredMixin, ListView):
	permission_required = "exams.view_exam"
	model = Exam
	template_name = "exams/exam_list.html"
	context_object_name = "exams"
	paginate_by = 25

	def get_queryset(self):
		return self.get_exam_queryset().order_by("-created_at")


class ExamDetailView(TeacherOwnedExamMixin, PermissionRequiredMixin, DetailView):
	permission_required = "exams.view_exam"
	model = Exam
	template_name = "exams/exam_detail.html"
	context_object_name = "exam"

	def get_queryset(self):
		return self.get_exam_queryset().prefetch_related("questions__choices")


class ExamCreateView(TeacherOwnedExamMixin, PermissionRequiredMixin, CreateView):
	permission_required = "exams.add_exam"
	model = Exam
	form_class = ExamForm
	template_name = "exams/exam_form.html"

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["teacher"] = self._require_teacher()
		return kwargs

	def form_valid(self, form):
		form.instance.teacher = self._require_teacher()
		messages.success(self.request, "Exam created successfully.")
		response = super().form_valid(form)
		_notify_new_exam_created(self.object)
		return response

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.object.pk])


class ExamUpdateView(TeacherOwnedExamMixin, PermissionRequiredMixin, UpdateView):
	permission_required = "exams.change_exam"
	model = Exam
	form_class = ExamForm
	template_name = "exams/exam_form.html"

	def get_queryset(self):
		return self.get_exam_queryset()

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["teacher"] = self._require_teacher()
		return kwargs

	def form_valid(self, form):
		messages.success(self.request, "Exam updated successfully.")
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.object.pk])


class ExamDeleteView(TeacherOwnedExamMixin, PermissionRequiredMixin, DeleteView):
	permission_required = "exams.delete_exam"
	model = Exam
	template_name = "exams/exam_confirm_delete.html"

	def get_queryset(self):
		return self.get_exam_queryset()

	def get_success_url(self):
		messages.success(self.request, "Exam deleted successfully.")
		return reverse("exams:exam_list")


class ExamPublishToggleView(TeacherOwnedExamMixin, PermissionRequiredMixin, View):
	permission_required = "exams.change_exam"

	def post(self, request, pk):
		exam = get_object_or_404(self.get_exam_queryset(), pk=pk)
		became_published = False
		if exam.status == Exam.Status.PUBLISHED:
			if not request.user.has_perm("exams.unpublish_exam"):
				raise PermissionDenied("Missing unpublish permission.")
			exam.status = Exam.Status.DRAFT
			messages.success(request, "Exam unpublished successfully.")
		else:
			if not request.user.has_perm("exams.publish_exam"):
				raise PermissionDenied("Missing publish permission.")
			exam.status = Exam.Status.PUBLISHED
			became_published = True
			messages.success(request, "Exam published successfully.")
		exam.save(update_fields=["status", "updated_at"])
		if became_published:
			_notify_exam_published(exam)
		return redirect("exams:exam_detail", pk=exam.pk)


class QuestionCreateView(TeacherOwnedExamMixin, PermissionRequiredMixin, CreateView):
	permission_required = "exams.add_question"
	model = Question
	form_class = QuestionForm
	template_name = "exams/question_form.html"

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		return super().dispatch(request, *args, **kwargs)

	def form_valid(self, form):
		form.instance.exam = self.exam
		messages.success(self.request, "Question added successfully.")
		return super().form_valid(form)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		return context

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.exam.pk])


class QuestionUpdateView(TeacherOwnedExamMixin, PermissionRequiredMixin, UpdateView):
	permission_required = "exams.change_question"
	model = Question
	form_class = QuestionForm
	template_name = "exams/question_form.html"

	def get_queryset(self):
		return Question.objects.filter(exam__in=self.get_exam_queryset(), exam_id=self.kwargs["exam_pk"])

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		return super().dispatch(request, *args, **kwargs)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		return context

	def form_valid(self, form):
		messages.success(self.request, "Question updated successfully.")
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.exam.pk])


class QuestionDeleteView(TeacherOwnedExamMixin, PermissionRequiredMixin, DeleteView):
	permission_required = "exams.delete_question"
	model = Question
	template_name = "exams/question_confirm_delete.html"

	def get_queryset(self):
		return Question.objects.filter(exam__in=self.get_exam_queryset(), exam_id=self.kwargs["exam_pk"])

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		return super().dispatch(request, *args, **kwargs)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		return context

	def get_success_url(self):
		messages.success(self.request, "Question deleted successfully.")
		return reverse("exams:exam_detail", args=[self.exam.pk])


class ChoiceCreateView(TeacherOwnedExamMixin, PermissionRequiredMixin, CreateView):
	permission_required = "exams.add_choice"
	model = Choice
	form_class = ChoiceForm
	template_name = "exams/choice_form.html"

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		self.question = get_object_or_404(Question, pk=self.kwargs["question_pk"], exam=self.exam)
		return super().dispatch(request, *args, **kwargs)

	def form_valid(self, form):
		form.instance.question = self.question
		messages.success(self.request, "Choice added successfully.")
		return super().form_valid(form)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		context["question"] = self.question
		return context

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.exam.pk])


class ChoiceUpdateView(TeacherOwnedExamMixin, PermissionRequiredMixin, UpdateView):
	permission_required = "exams.change_choice"
	model = Choice
	form_class = ChoiceForm
	template_name = "exams/choice_form.html"

	def get_queryset(self):
		return Choice.objects.filter(
			question__exam__in=self.get_exam_queryset(),
			question__exam_id=self.kwargs["exam_pk"],
			question_id=self.kwargs["question_pk"],
		)

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		self.question = get_object_or_404(Question, pk=self.kwargs["question_pk"], exam=self.exam)
		return super().dispatch(request, *args, **kwargs)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		context["question"] = self.question
		return context

	def form_valid(self, form):
		messages.success(self.request, "Choice updated successfully.")
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("exams:exam_detail", args=[self.exam.pk])


class ChoiceDeleteView(TeacherOwnedExamMixin, PermissionRequiredMixin, DeleteView):
	permission_required = "exams.delete_choice"
	model = Choice
	template_name = "exams/choice_confirm_delete.html"

	def get_queryset(self):
		return Choice.objects.filter(
			question__exam__in=self.get_exam_queryset(),
			question__exam_id=self.kwargs["exam_pk"],
			question_id=self.kwargs["question_pk"],
		)

	def dispatch(self, request, *args, **kwargs):
		self.exam = self.get_exam(self.kwargs["exam_pk"])
		self.question = get_object_or_404(Question, pk=self.kwargs["question_pk"], exam=self.exam)
		return super().dispatch(request, *args, **kwargs)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["exam"] = self.exam
		context["question"] = self.question
		return context

	def get_success_url(self):
		messages.success(self.request, "Choice deleted successfully.")
		return reverse("exams:exam_detail", args=[self.exam.pk])


class StudentExamListView(StudentOwnedExamMixin, PermissionRequiredMixin, ListView):
	permission_required = "exams.view_exam"
	model = Exam
	template_name = "exams/student_exam_list.html"
	context_object_name = "exams"
	paginate_by = 25

	def dispatch(self, request, *args, **kwargs):
		self._require_student()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._student_exam_queryset().prefetch_related("questions").order_by("-created_at")


class StudentExamDetailView(StudentOwnedExamMixin, PermissionRequiredMixin, DetailView):
	permission_required = "exams.view_exam"
	model = Exam
	template_name = "exams/student_exam_detail.html"
	context_object_name = "exam"

	def dispatch(self, request, *args, **kwargs):
		self.student = self._require_student()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._student_exam_queryset().prefetch_related("questions__choices")

	def get_student_exam_submission(self):
		return (
			StudentExam.objects.filter(exam=self.object, student=self.student)
			.prefetch_related("answers__question", "answers__selected_choice")
			.order_by("attempt_no", "pk")
			.first()
		)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		student_exam = self.get_student_exam_submission()
		context["student_exam"] = student_exam
		context["exam_state"] = self.object.availability_state()
		context["can_submit"] = self.object.is_available_to_students() and not (
			student_exam and student_exam.submitted_at is not None
		)
		if context["can_submit"]:
			context["form"] = kwargs.get("form") or StudentExamSubmissionForm(exam=self.object)
		else:
			context["form"] = None
		return context

	def post(self, request, *args, **kwargs):
		self.object = self.get_object()
		self.student = self._require_student()
		if not request.user.has_perm("exams.add_studentexam"):
			raise PermissionDenied("Missing exam submission permission.")
		if not self.object.is_available_to_students():
			raise PermissionDenied("Exam is not available right now.")

		existing_submission = self.get_student_exam_submission()
		if existing_submission and existing_submission.submitted_at is not None:
			raise PermissionDenied("This exam has already been submitted.")

		form = StudentExamSubmissionForm(self.request.POST, exam=self.object)
		if not form.is_valid():
			context = self.get_context_data(form=form)
			return self.render_to_response(context)

		with transaction.atomic():
			student_exam, _ = StudentExam.objects.get_or_create(
				exam=self.object,
				student=self.student,
				defaults={"attempt_no": 1, "status": StudentExam.Status.STARTED},
			)
			if student_exam.submitted_at is not None:
				raise PermissionDenied("This exam has already been submitted.")
			if not student_exam.started_at:
				student_exam.started_at = timezone.now()
			student_exam.status = StudentExam.Status.STARTED
			student_exam.save(update_fields=["started_at", "status", "updated_at"])

			StudentAnswer.objects.filter(student_exam=student_exam).delete()
			for question in self.object.questions.all():
				field_name = f"question_{question.pk}"
				value = form.cleaned_data[field_name]
				answer = StudentAnswer(student_exam=student_exam, question=question)
				if question.question_type == Question.QuestionType.ESSAY:
					answer.answer_text = value.strip()
					answer.is_correct = None
					answer.score = None
				else:
					answer.selected_choice_id = int(value)
					answer.is_correct = bool(answer.selected_choice and answer.selected_choice.is_correct)
					answer.score = question.marks if answer.is_correct else 0
				answer.full_clean()
				answer.save()

			was_graded = student_exam.status == StudentExam.Status.GRADED
			student_exam.status = StudentExam.Status.SUBMITTED
			student_exam.submitted_at = timezone.now()
			student_exam.save(update_fields=["status", "submitted_at", "updated_at"])
			student_exam.recalculate_result()
			if not was_graded and student_exam.status == StudentExam.Status.GRADED:
				_notify_exam_graded(student_exam)

		messages.success(request, "Exam submitted successfully.")
		return redirect("exams:student_exam_detail", pk=self.object.pk)


class StudentExamResultView(StudentOwnedExamMixin, PermissionRequiredMixin, DetailView):
	permission_required = "exams.view_studentexam"
	model = Exam
	template_name = "exams/student_exam_result.html"
	context_object_name = "exam"

	def dispatch(self, request, *args, **kwargs):
		self.student = self._require_student()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._student_exam_queryset().prefetch_related("questions__choices")

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		student_exam = (
			StudentExam.objects.filter(exam=self.object, student=self.student)
			.prefetch_related("answers__question", "answers__selected_choice")
			.order_by("attempt_no", "pk")
			.first()
		)
		if student_exam is None:
			raise PermissionDenied("No submitted result found for this exam.")
		context["student_exam"] = student_exam
		context["answers"] = student_exam.answers.select_related("question", "selected_choice").order_by(
			"question__display_order", "question_id"
		)
		return context


class TeacherResultListView(TeacherOwnedExamMixin, PermissionRequiredMixin, ListView):
	permission_required = "exams.view_studentexam"
	model = StudentExam
	template_name = "exams/result_list.html"
	context_object_name = "student_exams"
	paginate_by = 30

	def get_queryset(self):
		return (
			StudentExam.objects.filter(exam__in=self.get_exam_queryset())
			.select_related("exam", "student", "student__account", "student__account__user")
			.order_by("-submitted_at", "-created_at")
		)


class TeacherExamReportListView(TeacherOwnedExamMixin, PermissionRequiredMixin, ListView):
	permission_required = "exams.view_studentexam"
	model = Exam
	template_name = "exams/report_list.html"
	context_object_name = "exam_reports"
	paginate_by = 30

	def get_queryset(self):
		return (
			self.get_exam_queryset()
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
				avg_score=Coalesce(
					Avg("student_exams__score"),
					Value(0, output_field=DecimalField(max_digits=7, decimal_places=2)),
					output_field=DecimalField(max_digits=7, decimal_places=2),
				),
				avg_percentage=Coalesce(
					Avg("student_exams__percentage"),
					Value(0, output_field=DecimalField(max_digits=5, decimal_places=2)),
					output_field=DecimalField(max_digits=5, decimal_places=2),
				),
			)
			.order_by("-created_at")
		)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		exams = context["exam_reports"]
		total_exams = exams.paginator.count if hasattr(exams, "paginator") else len(exams)
		total_submitted = sum(item.submitted_attempts for item in exams)
		total_graded = sum(item.graded_attempts for item in exams)
		total_passed = sum(item.passed_attempts for item in exams)
		pass_rate = round((total_passed * 100 / total_graded), 1) if total_graded else 0.0
		context.update(
			{
				"total_exams": total_exams,
				"total_submitted_attempts": total_submitted,
				"total_graded_attempts": total_graded,
				"total_passed_attempts": total_passed,
				"overall_pass_rate": pass_rate,
			}
		)
		return context


class TeacherEssayGradeView(TeacherOwnedExamMixin, PermissionRequiredMixin, View):
	permission_required = "exams.change_studentanswer"
	template_name = "exams/result_grade.html"

	def get_student_exam_queryset(self):
		return StudentExam.objects.filter(exam__in=self.get_exam_queryset()).select_related(
			"exam", "student", "student__account", "student__account__user"
		)

	def get_student_exam(self):
		return get_object_or_404(self.get_student_exam_queryset(), pk=self.kwargs["student_exam_pk"])

	def get(self, request, *args, **kwargs):
		student_exam = self.get_student_exam()
		form = EssayManualGradeForm(student_exam=student_exam)
		essay_answers = student_exam.answers.select_related("question").filter(
			question__question_type=Question.QuestionType.ESSAY
		).order_by("question__display_order", "question_id")
		essay_form_rows = [(answer, form[f"essay_answer_{answer.pk}"]) for answer in essay_answers]
		return self.render_to_response(
			{
				"student_exam": student_exam,
				"essay_answers": essay_answers,
				"essay_form_rows": essay_form_rows,
				"form": form,
			}
		)

	def post(self, request, *args, **kwargs):
		student_exam = self.get_student_exam()
		form = EssayManualGradeForm(request.POST, student_exam=student_exam)
		if not form.is_valid():
			essay_answers = student_exam.answers.select_related("question").filter(
				question__question_type=Question.QuestionType.ESSAY
			).order_by("question__display_order", "question_id")
			essay_form_rows = [(answer, form[f"essay_answer_{answer.pk}"]) for answer in essay_answers]
			return self.render_to_response(
				{
					"student_exam": student_exam,
					"essay_answers": essay_answers,
					"essay_form_rows": essay_form_rows,
					"form": form,
				}
			)

		with transaction.atomic():
			was_graded = student_exam.status == StudentExam.Status.GRADED
			for answer in form.essay_answers:
				field_name = f"essay_answer_{answer.pk}"
				answer.score = form.cleaned_data[field_name]
				answer.is_correct = None
				answer.full_clean()
				answer.save(update_fields=["score", "is_correct", "updated_at"])
			student_exam.grader_notes = form.cleaned_data.get("grader_notes", "")
			student_exam.save(update_fields=["grader_notes", "updated_at"])
			student_exam.recalculate_result()
			if not was_graded and student_exam.status == StudentExam.Status.GRADED:
				_notify_exam_graded(student_exam)

		messages.success(request, "Essay grading saved successfully.")
		return redirect("exams:result_grade", student_exam_pk=student_exam.pk)

	def render_to_response(self, context):
		return render(self.request, self.template_name, context)
