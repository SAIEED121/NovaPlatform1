from django.contrib import admin
from .models import SubscriptionPlan, PlanCourse, StudentSubscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "duration_days", "price", "status", "created_at", "updated_at")
	list_filter = ("status", "created_at", "updated_at")
	search_fields = ("name",)
	ordering = ("name",)
	readonly_fields = ("created_at", "updated_at")
	list_per_page = 25

	fieldsets = (
		("Plan", {
			"fields": ("name", "description"),
		}),
		("Billing", {
			"fields": ("duration_days", "price", "status"),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)


@admin.register(PlanCourse)
class PlanCourseAdmin(admin.ModelAdmin):
	list_display = ("id", "plan", "course", "created_at", "updated_at")
	list_filter = ("created_at",)
	search_fields = ("plan__name", "course__code", "course__title")
	ordering = ("plan__name", "course__code")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("plan", "course")
	list_per_page = 25

	fieldsets = (
		("Mapping", {
			"fields": ("plan", "course"),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)


@admin.register(StudentSubscription)
class StudentSubscriptionAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"student",
		"plan",
		"status",
		"auto_renew",
		"started_at",
		"ends_at",
		"created_at",
	)
	list_filter = ("status", "auto_renew", "started_at", "ends_at")
	search_fields = (
		"student__student_code",
		"student__account__user__username",
		"plan__name",
	)
	ordering = ("-started_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("student", "student__account", "student__account__user", "plan")
	list_per_page = 25

	fieldsets = (
		("Subscription", {
			"fields": ("student", "plan", "status", "auto_renew"),
		}),
		("Timeline", {
			"fields": ("started_at", "ends_at"),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)
