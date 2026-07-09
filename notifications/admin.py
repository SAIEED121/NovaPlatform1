from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"title",
		"recipient_type",
		"channel",
		"status",
		"admin_user",
		"student",
		"teacher",
		"sent_at",
		"read_at",
	)
	list_filter = ("recipient_type", "channel", "status", "sent_at")
	search_fields = (
		"title",
		"message",
		"admin_user__username",
		"student__student_code",
		"teacher__employee_code",
	)
	ordering = ("-created_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("admin_user", "student", "teacher")
	list_per_page = 25

	fieldsets = (
		("Content", {
			"fields": ("title", "message"),
		}),
		("Delivery", {
			"fields": ("channel", "status", "sent_at", "read_at"),
		}),
		("Recipient", {
			"fields": ("recipient_type", "admin_user", "student", "teacher"),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)
