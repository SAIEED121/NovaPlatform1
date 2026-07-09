from django.contrib import admin
from .forms import TeacherForm
from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
	form = TeacherForm
	list_display = (
		"id",
		"employee_code",
		"account",
		"specialization",
		"years_of_experience",
		"status",
		"hired_at",
		"created_at",
	)
	list_filter = ("status", "specialization", "years_of_experience", "hired_at", "created_at")
	search_fields = (
		"employee_code",
		"specialization",
		"account__user__username",
		"account__user__first_name",
		"account__user__last_name",
	)
	ordering = ("employee_code",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("account", "account__user")
	list_per_page = 25

	fieldsets = (
		("Identity", {
			"fields": ("account", "employee_code", "status"),
		}),
		("Professional", {
			"fields": ("specialization", "years_of_experience", "hired_at"),
		}),
		("Profile", {
			"fields": ("bio",),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)
