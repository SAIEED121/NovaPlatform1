from django.contrib import admin
from .models import Invoice, Payment, Receipt


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"student",
		"requested_by",
		"approved_by",
		"subscription",
		"amount",
		"currency",
		"method",
		"status",
		"transaction_reference",
		"paid_at",
		"created_at",
	)
	list_filter = ("method", "status", "currency", "approved_at", "created_at")
	search_fields = (
		"student__student_code",
		"student__account__user__username",
		"requested_by__username",
		"approved_by__username",
		"transaction_reference",
		"notes",
	)
	ordering = ("-created_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = (
		"student",
		"student__account",
		"student__account__user",
		"requested_by",
		"approved_by",
		"subscription",
	)
	list_per_page = 25

	fieldsets = (
		("Payment", {
			"fields": ("student", "requested_by", "approved_by", "subscription", "amount", "currency"),
		}),
		("Processing", {
			"fields": ("method", "status", "transaction_reference", "paid_at", "approved_at"),
		}),
		("Additional", {
			"fields": ("notes",),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"invoice_number",
		"payment",
		"total_amount",
		"currency",
		"status",
		"issued_at",
	)
	list_filter = ("status", "currency", "issued_at")
	search_fields = (
		"invoice_number",
		"payment__student__student_code",
		"payment__transaction_reference",
	)
	ordering = ("-issued_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("payment", "payment__student")
	list_per_page = 25


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"receipt_number",
		"payment",
		"amount",
		"currency",
		"method",
		"issued_at",
	)
	list_filter = ("currency", "method", "issued_at")
	search_fields = (
		"receipt_number",
		"payment__student__student_code",
		"transaction_reference",
	)
	ordering = ("-issued_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("payment", "payment__student")
	list_per_page = 25
