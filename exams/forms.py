from django import forms
from decimal import Decimal

from courses.models import Course

from .models import Choice, Exam, Question


class ExamForm(forms.ModelForm):
	class Meta:
		model = Exam
		fields = [
			"title",
			"description",
			"course",
			"status",
			"start_at",
			"end_at",
			"duration_minutes",
			"total_marks",
			"passing_marks",
			"allow_late_submission",
		]
		widgets = {
			"description": forms.Textarea(attrs={"rows": 4}),
			"start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
			"end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
		}

	def __init__(self, *args, **kwargs):
		self.teacher = kwargs.pop("teacher", None)
		super().__init__(*args, **kwargs)
		self.fields["start_at"].input_formats = ["%Y-%m-%dT%H:%M"]
		self.fields["end_at"].input_formats = ["%Y-%m-%dT%H:%M"]

		if self.teacher is not None:
			self.fields["course"].queryset = Course.objects.filter(teacher=self.teacher).order_by("code")
		else:
			self.fields["course"].queryset = Course.objects.none()

	def clean_course(self):
		course = self.cleaned_data["course"]
		if self.teacher is None or course.teacher_id != self.teacher.id:
			raise forms.ValidationError("You can only assign exams to your own courses.")
		return course


class QuestionForm(forms.ModelForm):
	class Meta:
		model = Question
		fields = ["text", "question_type", "marks", "display_order"]
		widgets = {
			"text": forms.Textarea(attrs={"rows": 4}),
		}


class ChoiceForm(forms.ModelForm):
	class Meta:
		model = Choice
		fields = ["text", "is_correct", "display_order"]


class StudentExamSubmissionForm(forms.Form):
	def __init__(self, *args, **kwargs):
		self.exam = kwargs.pop("exam")
		super().__init__(*args, **kwargs)
		self.questions = list(
			self.exam.questions.prefetch_related("choices").order_by("display_order", "id")
		)

		for question in self.questions:
			field_name = f"question_{question.pk}"
			field_label = f"{question.display_order}. {question.text}"
			if question.question_type == Question.QuestionType.ESSAY:
				self.fields[field_name] = forms.CharField(
					label=field_label,
					widget=forms.Textarea(attrs={"rows": 4}),
				)
			else:
				self.fields[field_name] = forms.ChoiceField(
					label=field_label,
					choices=[(str(choice.pk), choice.text) for choice in question.choices.all()],
					widget=forms.RadioSelect,
				)


class EssayManualGradeForm(forms.Form):
	def __init__(self, *args, **kwargs):
		self.student_exam = kwargs.pop("student_exam")
		super().__init__(*args, **kwargs)
		self.essay_answers = list(
			self.student_exam.answers.select_related("question")
			.filter(question__question_type=Question.QuestionType.ESSAY)
			.order_by("question__display_order", "question_id")
		)

		for answer in self.essay_answers:
			field_name = f"essay_answer_{answer.pk}"
			self.fields[field_name] = forms.DecimalField(
				label=f"Q{answer.question.display_order} ({answer.question.marks} marks)",
				required=True,
				min_value=Decimal("0"),
				max_digits=6,
				decimal_places=2,
				initial=answer.score,
			)

		self.fields["grader_notes"] = forms.CharField(
			label="Grader notes",
			required=False,
			widget=forms.Textarea(attrs={"rows": 3}),
			initial=self.student_exam.grader_notes,
		)

	def clean(self):
		cleaned_data = super().clean()
		for answer in self.essay_answers:
			field_name = f"essay_answer_{answer.pk}"
			value = cleaned_data.get(field_name)
			if value is None:
				continue
			if value > answer.question.marks:
				self.add_error(field_name, "Essay score cannot exceed question marks.")
		return cleaned_data
