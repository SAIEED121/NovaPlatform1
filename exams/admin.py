from django.contrib import admin

from .models import Choice, Exam, Question, StudentAnswer, StudentExam


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"title",
		"teacher",
		"course",
		"status",
		"start_at",
		"end_at",
	)
	list_filter = ("status", "teacher", "course")
	search_fields = ("title", "course__code", "course__title", "teacher__employee_code")
	ordering = ("-created_at",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
	list_display = ("id", "exam", "display_order", "question_type", "marks")
	list_filter = ("question_type",)
	search_fields = ("exam__title", "text")
	ordering = ("exam", "display_order")


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
	list_display = ("id", "question", "display_order", "is_correct")
	list_filter = ("is_correct",)
	search_fields = ("question__text", "text")
	ordering = ("question", "display_order")


@admin.register(StudentExam)
class StudentExamAdmin(admin.ModelAdmin):
	list_display = ("id", "exam", "student", "attempt_no", "status", "score")
	list_filter = ("status",)
	search_fields = ("exam__title", "student__student_code")
	ordering = ("-created_at",)


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
	list_display = ("id", "student_exam", "question", "selected_choice", "is_correct", "score")
	list_filter = ("is_correct",)
	search_fields = ("question__text", "answer_text")
	ordering = ("student_exam", "question")
