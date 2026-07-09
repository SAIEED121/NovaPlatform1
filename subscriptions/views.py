from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import PlanCourseForm, StudentSubscriptionForm, SubscriptionPlanForm
from .models import PlanCourse, StudentSubscription, SubscriptionPlan
from students.models import Student


def _base_student_subscription_queryset():
	return StudentSubscription.objects.select_related(
		"student",
		"student__account",
		"student__account__user",
		"plan",
	)


def _student_profile(user):
	return Student.objects.select_related("account", "account__user").filter(account__user=user).first()


def _visible_student_subscription_queryset(user):
	queryset = _base_student_subscription_queryset()
	if user and user.is_authenticated and (user.is_superuser or user.is_staff):
		return queryset

	student_profile = _student_profile(user)
	if student_profile:
		return queryset.filter(student=student_profile)

	return queryset.none()


class AutoExpireSubscriptionsMixin:
	def dispatch(self, request, *args, **kwargs):
		StudentSubscription.objects.auto_expire()
		return super().dispatch(request, *args, **kwargs)


class SubscriptionPlanListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = SubscriptionPlan
	permission_required = "subscriptions.view_subscriptionplan"
	template_name = "subscriptions/subscription_plan_list.html"
	context_object_name = "plans"
	paginate_by = 25


class SubscriptionPlanDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = SubscriptionPlan
	permission_required = "subscriptions.view_subscriptionplan"
	template_name = "subscriptions/subscription_plan_detail.html"
	context_object_name = "plan"

	def get_queryset(self):
		return SubscriptionPlan.objects.prefetch_related("plan_courses__course")


class SubscriptionPlanCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = SubscriptionPlan
	form_class = SubscriptionPlanForm
	permission_required = "subscriptions.add_subscriptionplan"
	template_name = "subscriptions/subscription_plan_form.html"
	success_url = reverse_lazy("subscriptions:plan_list")


class SubscriptionPlanUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = SubscriptionPlan
	form_class = SubscriptionPlanForm
	permission_required = "subscriptions.change_subscriptionplan"
	template_name = "subscriptions/subscription_plan_form.html"
	success_url = reverse_lazy("subscriptions:plan_list")


class SubscriptionPlanDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = SubscriptionPlan
	permission_required = "subscriptions.delete_subscriptionplan"
	template_name = "subscriptions/subscription_plan_confirm_delete.html"
	success_url = reverse_lazy("subscriptions:plan_list")


class PlanCourseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = PlanCourse
	permission_required = "subscriptions.view_plancourse"
	template_name = "subscriptions/plan_course_list.html"
	context_object_name = "plan_courses"
	paginate_by = 25

	def get_queryset(self):
		return PlanCourse.objects.select_related("plan", "course").order_by(
			"plan__name",
			"course__code",
			"pk",
		)


class PlanCourseDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = PlanCourse
	permission_required = "subscriptions.view_plancourse"
	template_name = "subscriptions/plan_course_detail.html"
	context_object_name = "plan_course"

	def get_queryset(self):
		return PlanCourse.objects.select_related("plan", "course")


class PlanCourseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = PlanCourse
	form_class = PlanCourseForm
	permission_required = "subscriptions.add_plancourse"
	template_name = "subscriptions/plan_course_form.html"
	success_url = reverse_lazy("subscriptions:plan_course_list")


class PlanCourseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = PlanCourse
	form_class = PlanCourseForm
	permission_required = "subscriptions.change_plancourse"
	template_name = "subscriptions/plan_course_form.html"
	success_url = reverse_lazy("subscriptions:plan_course_list")


class PlanCourseDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = PlanCourse
	permission_required = "subscriptions.delete_plancourse"
	template_name = "subscriptions/plan_course_confirm_delete.html"
	success_url = reverse_lazy("subscriptions:plan_course_list")


class StudentSubscriptionListView(AutoExpireSubscriptionsMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = StudentSubscription
	permission_required = "subscriptions.view_studentsubscription"
	template_name = "subscriptions/student_subscription_list.html"
	context_object_name = "student_subscriptions"
	paginate_by = 25

	def get_queryset(self):
		return _visible_student_subscription_queryset(self.request.user)


class StudentSubscriptionDetailView(AutoExpireSubscriptionsMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = StudentSubscription
	permission_required = "subscriptions.view_studentsubscription"
	template_name = "subscriptions/student_subscription_detail.html"
	context_object_name = "student_subscription"

	def get_queryset(self):
		return _visible_student_subscription_queryset(self.request.user)


class StudentSubscriptionCreateView(AutoExpireSubscriptionsMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = StudentSubscription
	form_class = StudentSubscriptionForm
	permission_required = "subscriptions.add_studentsubscription"
	template_name = "subscriptions/student_subscription_form.html"
	success_url = reverse_lazy("subscriptions:student_subscription_list")


class StudentSubscriptionUpdateView(AutoExpireSubscriptionsMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = StudentSubscription
	form_class = StudentSubscriptionForm
	permission_required = "subscriptions.change_studentsubscription"
	template_name = "subscriptions/student_subscription_form.html"
	success_url = reverse_lazy("subscriptions:student_subscription_list")

	def get_queryset(self):
		return _visible_student_subscription_queryset(self.request.user)

class StudentSubscriptionDeleteView(AutoExpireSubscriptionsMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = StudentSubscription
	permission_required = "subscriptions.delete_studentsubscription"
	template_name = "subscriptions/student_subscription_confirm_delete.html"
	success_url = reverse_lazy("subscriptions:student_subscription_list")

	def get_queryset(self):
		return _visible_student_subscription_queryset(self.request.user)
