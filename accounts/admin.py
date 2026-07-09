from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from .models import (
	ActivityLog,
	AccountProfile,
	CustomPermission,
	LoginAttemptLog,
	LoginIPBlock,
	LoginSecurity,
	RoleCustomPermission,
	SuspiciousActivity,
	UserCustomPermission,
)


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "role", "status", "phone_number", "country", "profile_photo", "last_seen_at", "created_at")
	list_filter = ("role", "status", "country", "created_at", "updated_at")
	search_fields = ("user__username", "user__first_name", "user__last_name", "phone_number", "country")
	ordering = ("-created_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("user",)
	list_per_page = 25

	fieldsets = (
		("Identity", {
			"fields": ("user", "role", "status"),
		}),
		("Contact", {
			"fields": ("phone_number", "country", "profile_photo"),
		}),
		("Activity", {
			"fields": ("last_seen_at",),
		}),
		("Audit", {
			"fields": ("created_at", "updated_at"),
		}),
	)


@admin.register(CustomPermission)
class CustomPermissionAdmin(admin.ModelAdmin):
	list_display = ("id", "code", "name", "is_active", "created_at")
	list_filter = ("is_active", "created_at")
	search_fields = ("code", "name", "description")
	ordering = ("code",)
	readonly_fields = ("created_at", "updated_at")
	list_per_page = 25


@admin.register(RoleCustomPermission)
class RoleCustomPermissionAdmin(admin.ModelAdmin):
	list_display = ("id", "role", "permission", "is_granted", "created_at")
	list_filter = ("role", "is_granted", "created_at")
	search_fields = ("permission__code", "permission__name")
	ordering = ("role", "permission__code")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("permission",)
	list_per_page = 25


@admin.register(UserCustomPermission)
class UserCustomPermissionAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "permission", "is_granted", "created_at")
	list_filter = ("is_granted", "created_at")
	search_fields = ("user__username", "permission__code", "permission__name", "notes")
	ordering = ("user__username", "permission__code")
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("user", "permission")
	list_per_page = 25


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
	list_display = ("id", "created_at", "actor", "event_type", "action", "target_model", "target_id", "ip_address")
	list_filter = ("event_type", "action", "target_model", "created_at")
	search_fields = ("actor__username", "target_model", "target_id", "description")
	ordering = ("-created_at",)
	readonly_fields = (
		"created_at",
		"actor",
		"event_type",
		"action",
		"target_model",
		"target_id",
		"description",
		"metadata",
		"ip_address",
	)
	list_select_related = ("actor",)
	list_per_page = 50


@admin.register(LoginSecurity)
class LoginSecurityAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"user",
		"failed_login_attempts",
		"is_locked",
		"locked_at",
		"last_failed_login",
		"last_failed_ip",
		"last_successful_login",
		"last_successful_ip",
		"updated_at",
	)
	list_filter = ("is_locked", "locked_at", "updated_at")
	search_fields = ("user__username", "user__email")
	ordering = ("-updated_at",)
	readonly_fields = ("created_at", "updated_at")
	list_select_related = ("user",)
	list_per_page = 50
	actions = ("unlock_accounts", "reset_failed_attempts")

	@admin.action(description="Unlock selected accounts")
	def unlock_accounts(self, request, queryset):
		updated = 0
		with transaction.atomic():
			for security in queryset.select_for_update().select_related("user"):
				was_locked = security.is_locked
				security.failed_login_attempts = 0
				security.is_locked = False
				security.locked_at = None
				security.save(update_fields=["failed_login_attempts", "is_locked", "locked_at", "updated_at"])
				updated += 1
				if was_locked:
					LoginAttemptLog.objects.create(
						user=security.user,
						username=security.user.username,
						is_successful=True,
						failure_reason="account_unlocked",
						role_key="admin_action",
						is_unlock_event=True,
						unlocked_by=request.user,
						unlock_reason="Admin action: unlock selected accounts",
					)
		self.message_user(request, f"Unlocked {updated} account(s).")

	@admin.action(description="Reset failed attempts")
	def reset_failed_attempts(self, request, queryset):
		updated = queryset.update(failed_login_attempts=0, updated_at=timezone.now())
		self.message_user(request, f"Reset failed attempts for {updated} account(s).")

	def get_actions(self, request):
		actions = super().get_actions(request)
		if not request.user.has_perm("accounts.unlock_loginsecurity"):
			actions.pop("unlock_accounts", None)
			actions.pop("reset_failed_attempts", None)
		return actions


@admin.register(LoginAttemptLog)
class LoginAttemptLogAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"attempted_at",
		"username",
		"user",
		"unlocked_by",
		"role_key",
		"is_successful",
		"is_lock_event",
		"is_unlock_event",
		"failure_reason",
		"ip_address",
		"browser",
		"operating_system",
	)
	list_filter = ("is_successful", "is_lock_event", "is_unlock_event", "role_key", "failure_reason", "attempted_at")
	search_fields = ("username", "user__username", "ip_address", "user_agent", "browser", "operating_system")
	ordering = ("-attempted_at",)
	readonly_fields = (
		"attempted_at",
		"username",
		"user",
		"unlocked_by",
		"unlock_reason",
		"role_key",
		"is_successful",
		"is_lock_event",
		"is_unlock_event",
		"failure_reason",
		"ip_address",
		"user_agent",
		"browser",
		"operating_system",
	)
	list_select_related = ("user", "unlocked_by")
	list_per_page = 100

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(LoginIPBlock)
class LoginIPBlockAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"ip_address",
		"failed_attempts",
		"first_failed_at",
		"last_failed_at",
		"blocked_until",
		"updated_at",
	)
	list_filter = ("blocked_until", "updated_at")
	search_fields = ("ip_address",)
	ordering = ("-updated_at",)
	readonly_fields = ("created_at", "updated_at")
	list_per_page = 100
	actions = ("unblock_ips",)

	@admin.action(description="Unblock selected IP addresses")
	def unblock_ips(self, request, queryset):
		updated = queryset.update(
			failed_attempts=0,
			first_failed_at=None,
			last_failed_at=None,
			blocked_until=None,
			updated_at=timezone.now(),
		)
		self.message_user(request, f"Unblocked {updated} IP address(es).")


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"event_type",
		"ip_address",
		"username",
		"observed_count",
		"threshold",
		"sample_count",
		"last_seen_at",
	)
	list_filter = ("event_type", "last_seen_at")
	search_fields = ("ip_address", "username")
	ordering = ("-last_seen_at",)
	readonly_fields = (
		"event_type",
		"ip_address",
		"username",
		"window_seconds",
		"threshold",
		"observed_count",
		"sample_count",
		"details",
		"detected_at",
		"last_seen_at",
	)
	list_per_page = 100
