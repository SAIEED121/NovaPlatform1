from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"student_code",
		"account",
		"grade_level",
		"branch",
		"status",
		"joined_at",
		"created_at",
	)
	list_filter = ("grade_level", "branch", "status", "joined_at", "created_at", "updated_at")
	search_fields = (
		"student_code",
		"account__user__username",
		"account__user__first_name",
		"account__user__last_name",
		"guardian_name",
		"guardian_phone",
	)
	ordering = ("student_code",)
	readonly_fields = ("joined_at", "created_at", "updated_at")
	list_select_related = ("account", "account__user")
	list_per_page = 25

	fieldsets = (
		("Identity", {
			"fields": ("account", "student_code", "status"),
		}),
		("Academic", {
			"fields": ("grade_level", "branch"),
		}),
		("Personal", {
			"fields": ("date_of_birth",),
		}),
		("Guardian", {
			"fields": ("guardian_name", "guardian_phone"),
		}),
		("Audit", {
			"fields": ("joined_at", "created_at", "updated_at"),
		}),
	)
