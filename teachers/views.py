from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, FormView, ListView, UpdateView

from accounts.models import AccountProfile
from .forms import AdminTeacherCreateForm, TeacherForm
from .models import Teacher


UserModel = get_user_model()


def _base_teacher_queryset():
	return Teacher.objects.select_related("account", "account__user")


def _visible_teachers_queryset(user):
	queryset = _base_teacher_queryset()
	if user and user.is_authenticated and (user.is_superuser or user.is_staff or user.groups.filter(name="Administrator").exists()):
		return queryset
	return queryset.filter(account__user=user)


def _split_full_name(full_name):
	name_parts = full_name.split(maxsplit=1)
	first_name = name_parts[0]
	last_name = name_parts[1] if len(name_parts) > 1 else ""
	return first_name, last_name


def _teacher_code_for_profile(profile):
	return f"TCH-{profile.pk:06d}"


class TeacherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Teacher
	permission_required = "teachers.view_teacher"
	template_name = "teachers/teacher_list.html"
	context_object_name = "teachers"
	paginate_by = 25

	def get_queryset(self):
		return _visible_teachers_queryset(self.request.user)


class AdministratorOnlyMutationMixin(UserPassesTestMixin):
	def test_func(self):
		user = self.request.user
		return user.is_superuser or user.groups.filter(name="Administrator").exists()


class TeacherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Teacher
	permission_required = "teachers.view_teacher"
	template_name = "teachers/teacher_detail.html"
	context_object_name = "teacher"

	def get_queryset(self):
		return _visible_teachers_queryset(self.request.user)


class TeacherCreateView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, FormView):
	form_class = AdminTeacherCreateForm
	permission_required = "teachers.add_teacher"
	template_name = "teachers/teacher_form.html"
	success_url = reverse_lazy("teachers:teacher_list")

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
				role=AccountProfile.Role.TEACHER,
				status=AccountProfile.Status.ACTIVE,
			)
			teacher = Teacher.objects.create(
				account=profile,
				employee_code=_teacher_code_for_profile(profile),
				specialization=form.cleaned_data["specialization"],
				years_of_experience=form.cleaned_data["years_of_experience"],
				status=form.cleaned_data["status"],
			)

			courses = form.cleaned_data["courses"]
			for course in courses:
				course.teacher = teacher
				course.save(update_fields=["teacher", "updated_at"])

		messages.success(self.request, "Teacher account created successfully.")
		return super().form_valid(form)


class TeacherUpdateView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Teacher
	form_class = TeacherForm
	permission_required = "teachers.change_teacher"
	template_name = "teachers/teacher_form.html"
	success_url = reverse_lazy("teachers:teacher_list")


class TeacherDeleteView(AdministratorOnlyMutationMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Teacher
	permission_required = "teachers.delete_teacher"
	template_name = "teachers/teacher_confirm_delete.html"
	success_url = reverse_lazy("teachers:teacher_list")
