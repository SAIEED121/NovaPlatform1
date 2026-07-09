from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.models import AccountProfile
from .forms import NotificationForm
from .models import Notification


def _dashboard_url_name_for_user(user):
	if not user or not user.is_authenticated:
		return "home"
	if user.is_superuser or user.is_staff or user.groups.filter(name="Administrator").exists():
		return "admin_dashboard"
	profile = getattr(user, "account_profile", None)
	if not profile:
		return "home"
	if profile.role == AccountProfile.Role.TEACHER:
		return "teacher_dashboard"
	if profile.role == AccountProfile.Role.STUDENT:
		return "student_dashboard"
	if profile.role == AccountProfile.Role.PARENT:
		return "parent_dashboard"
	if profile.role == AccountProfile.Role.ADMIN:
		return "admin_dashboard"
	return "home"


class NotificationVisibilityMixin:
	def _base_queryset(self):
		return Notification.objects.select_related(
			"admin_user",
			"student",
			"student__account",
			"student__account__user",
			"teacher",
			"teacher__account",
			"teacher__account__user",
		)

	def _can_manage_all_notifications(self):
		user = self.request.user
		return bool(
			user
			and user.is_authenticated
			and (user.is_superuser or user.is_staff)
		)

	def _visible_queryset(self):
		if self._can_manage_all_notifications():
			return self._base_queryset()
		return Notification.objects.for_user(self.request.user).select_related(
			"admin_user",
			"student",
			"student__account",
			"student__account__user",
			"teacher",
			"teacher__account",
			"teacher__account__user",
		)


class NotificationListView(NotificationVisibilityMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Notification
	permission_required = "notifications.view_notification"
	template_name = "notifications/notification_list.html"
	context_object_name = "notifications"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_queryset()


class NotificationDetailView(NotificationVisibilityMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Notification
	permission_required = "notifications.view_notification"
	template_name = "notifications/notification_detail.html"
	context_object_name = "notification"

	def get_queryset(self):
		return self._visible_queryset()


class NotificationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Notification
	form_class = NotificationForm
	permission_required = "notifications.add_notification"
	template_name = "notifications/notification_form.html"
	success_url = reverse_lazy("notifications:notification_list")


class NotificationUpdateView(NotificationVisibilityMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Notification
	form_class = NotificationForm
	permission_required = "notifications.change_notification"
	template_name = "notifications/notification_form.html"
	success_url = reverse_lazy("notifications:notification_list")

	def get_queryset(self):
		return self._visible_queryset()


class NotificationDeleteView(NotificationVisibilityMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Notification
	permission_required = "notifications.delete_notification"
	template_name = "notifications/notification_confirm_delete.html"
	success_url = reverse_lazy("notifications:notification_list")

	def get_queryset(self):
		return self._visible_queryset()


class NotificationInboxView(LoginRequiredMixin, ListView):
	model = Notification
	template_name = "notifications/inbox.html"
	context_object_name = "notifications"
	paginate_by = 25

	def get_queryset(self):
		if hasattr(self, "_cached_queryset"):
			return self._cached_queryset

		self._cached_queryset = Notification.objects.for_user(self.request.user).select_related(
			"admin_user",
			"student",
			"student__account",
			"student__account__user",
			"teacher",
			"teacher__account",
			"teacher__account__user",
		)
		return self._cached_queryset

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["unread_count"] = self.get_queryset().filter(
			status=Notification.Status.UNREAD
		).count()
		profile = getattr(self.request.user, "account_profile", None)
		context["dashboard_url_name"] = _dashboard_url_name_for_user(self.request.user)
		context["can_access_teacher_exams"] = bool(
			profile and profile.role in {AccountProfile.Role.TEACHER, AccountProfile.Role.ADMIN}
		)
		context["can_access_student_exams"] = bool(
			profile and profile.role == AccountProfile.Role.STUDENT
		)
		return context


class NotificationMarkReadView(LoginRequiredMixin, View):
	def post(self, request, pk):
		notification = get_object_or_404(Notification.objects.for_user(request.user), pk=pk)
		notification.mark_as_read()
		messages.success(request, "Notification marked as read.")
		next_url = (request.POST.get("next") or "").strip()
		if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			return redirect(next_url)
		return redirect("notifications:inbox")


class NotificationMarkAllReadView(LoginRequiredMixin, View):
	def post(self, request):
		# Bulk update unread records for the current user in one query.
		updated = Notification.objects.unread_for_user(request.user).update(
			status=Notification.Status.READ,
			read_at=timezone.now(),
		)

		messages.success(request, f"Marked {updated} notifications as read.")
		next_url = (request.POST.get("next") or "").strip()
		if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			return redirect(next_url)
		return redirect("notifications:inbox")
