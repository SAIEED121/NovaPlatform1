from django.contrib import admin
from .models import Category, Course, Enrollment, HomeworkSubmission, Lesson, Schedule


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "status", "created_at")
	list_filter = ("status", "created_at")
	search_fields = ("name", "description")
	ordering = ("name",)
	readonly_fields = ("created_at", "updated_at")
	list_per_page = 25


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"code",
		"title",
		"teacher",
		"grade_level",
		"branch",
		"status",
		"price",
		"start_date",
		"end_date",
	)
	list_filter = ("status", "grade_level", "branch", "start_date", "end_date", "created_at")
	search_fields = (
		"code",
		"title",
		"description",
		"teacher__employee_code",
		"teacher__account__user__username",
		"teacher__account__user__first_name",
		"teacher__account__user__last_name",
	)
	ordering = ("code",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("teacher", "teacher__account", "teacher__account__user")
	list_per_page = 25

	fieldsets = (
		("Core", {
			"fields": ("code", "title", "description"),
		}),
		("Academic Scope", {
			"fields": ("teacher", "grade_level", "branch"),
		}),
		("Commercial", {
			"fields": ("price", "status"),
		}),
		("Schedule", {
			"fields": ("start_date", "end_date"),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
	list_display = ("id", "student", "course", "status", "progress_percent", "enrolled_at", "completed_at")
	list_filter = ("status", "enrolled_at", "completed_at")
	search_fields = (
		"student__student_code",
		"student__account__user__username",
		"course__code",
		"course__title",
	)
	ordering = ("-enrolled_at",)
	readonly_fields = ("enrolled_at", "created_at", "updated_at")
	list_select_related = (
		"student",
		"student__account",
		"student__account__user",
		"course",
	)
	list_per_page = 25

	fieldsets = (
		("Enrollment", {
			"fields": ("student", "course", "status"),
		}),
		("Progress", {
			"fields": ("progress_percent", "completed_at"),
		}),
		("Audit", {
			"fields": ("enrolled_at", "created_at", "updated_at"),
		}),
	)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
	list_display = ("id", "course", "order", "title", "duration_minutes", "is_published", "due_date")
	list_filter = ("is_published", "course", "due_date")
	search_fields = ("title", "description", "course__code", "course__title")
	ordering = ("course", "order")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("course",)
	list_per_page = 25


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
	list_display = ("id", "course", "lesson", "title", "starts_at", "ends_at", "is_live")
	list_filter = ("is_live", "starts_at", "course")
	search_fields = ("title", "notes", "course__code", "course__title", "lesson__title")
	ordering = ("-starts_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("course", "lesson")
	list_per_page = 25


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"enrollment",
		"lesson",
		"title",
		"attachment",
		"status",
		"grade",
		"submitted_at",
	)
	list_filter = ("status", "submitted_at", "reviewed_at")
	search_fields = (
		"title",
		"description",
		"enrollment__student__student_code",
		"enrollment__course__code",
	)
	ordering = ("-submitted_at",)
	readonly_fields = ("submitted_at", "created_at", "updated_at")
	list_select_related = ("enrollment", "lesson", "enrollment__student", "enrollment__course")
	list_per_page = 25
