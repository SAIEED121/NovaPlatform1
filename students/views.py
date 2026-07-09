from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DeleteView, DetailView, FormView, ListView, UpdateView

from accounts.models import AccountProfile
from courses.models import Enrollment
from subscriptions.models import StudentSubscription
from .forms import AdminStudentCreateForm, StudentForm
from .models import Student


UserModel = get_user_model()


def _split_full_name(full_name):
	name_parts = full_name.split(maxsplit=1)
	first_name = name_parts[0]
	last_name = name_parts[1] if len(name_parts) > 1 else ""
	return first_name, last_name


def _student_code_for_profile(profile):
	return f"STU-{profile.pk:06d}"


def _base_student_queryset():
	return Student.objects.select_related("account", "account__user")


def _visible_students_queryset(user):
	queryset = _base_student_queryset()
	if user and user.is_authenticated and (user.is_superuser or user.is_staff or user.groups.filter(name="Administrator").exists()):
		return queryset
	return queryset.filter(account__user=user)


class StudentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Student
	permission_required = "students.view_student"
	template_name = "students/student_list.html"
	context_object_name = "students"
	paginate_by = 25

	def get_queryset(self):
		return _visible_students_queryset(self.request.user)


class AdministratorOnlyMutationMixin(UserPassesTestMixin):
	def test_func(self):
		user = self.request.user
		return user.is_superuser or user.groups.filter(name="Administrator").exists()


class StudentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Student
	permission_required = "students.view_student"
	template_name = "students/student_detail.html"
	context_object_name = "student"

	def get_queryset(self):
		return _visible_students_queryset(self.request.user)


class StudentCreateView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, FormView):
	form_class = AdminStudentCreateForm
	permission_required = "students.add_student"
	template_name = "students/student_form.html"
	success_url = reverse_lazy("students:student_list")

	def form_valid(self, form):
		with transaction.atomic():
			first_name, last_name = _split_full_name(form.cleaned_data["full_name"])
			user = UserModel.objects.create_user(
				username=form.cleaned_data["username"],
				password=form.cleaned_data["password"],
				first_name=first_name,
				last_name=last_name,
			)
			profile = AccountProfile.objects.create(
				user=user,
				role=AccountProfile.Role.STUDENT,
				status=AccountProfile.Status.ACTIVE,
				phone_number=form.cleaned_data.get("phone_number", "").strip(),
			)
			student = Student.objects.create(
				account=profile,
				student_code=_student_code_for_profile(profile),
				grade_level=form.cleaned_data["grade_level"],
				branch=form.cleaned_data["branch"],
				status=form.cleaned_data["student_status"],
				guardian_name=form.cleaned_data.get("guardian_name", "").strip(),
				guardian_phone=form.cleaned_data.get("guardian_phone", "").strip(),
			)

			subscription_plan = form.cleaned_data.get("subscription_plan")
			if subscription_plan:
				started_at = timezone.now()
				StudentSubscription.objects.create(
					student=student,
					plan=subscription_plan,
					status=StudentSubscription.Status.ACTIVE,
					started_at=started_at,
					ends_at=started_at + timedelta(days=subscription_plan.duration_days),
				)

			for course in form.cleaned_data["courses"]:
				Enrollment.objects.create(
					student=student,
					course=course,
					status=Enrollment.Status.ACTIVE,
				)

		messages.success(self.request, "Student account created successfully.")
		return super().form_valid(form)


class StudentUpdateView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Student
	form_class = StudentForm
	permission_required = "students.change_student"
	template_name = "students/student_form.html"
	success_url = reverse_lazy("students:student_list")


class StudentDeleteView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Student
	permission_required = "students.delete_student"
	template_name = "students/student_confirm_delete.html"
	success_url = reverse_lazy("students:student_list")
