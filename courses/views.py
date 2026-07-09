from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (
	CategoryForm,
	CourseForm,
	EnrollmentForm,
	HomeworkSubmissionForm,
	LessonForm,
	ScheduleForm,
	TeacherAssignmentForm,
)
from .models import Category, Course, Enrollment, HomeworkSubmission, Lesson, Schedule
from students.models import Student
from teachers.models import Teacher


def _base_course_queryset():
	return Course.objects.select_related(
		"category",
		"teacher",
		"teacher__account",
		"teacher__account__user",
	)


def _base_enrollment_queryset():
	return Enrollment.objects.select_related(
		"student",
		"student__account",
		"student__account__user",
		"course",
		"course__category",
		"course__teacher",
		"course__teacher__account",
		"course__teacher__account__user",
	)


def _student_profile_for_user(user):
	return Student.objects.select_related("account", "account__user").filter(account__user=user).first()


def _teacher_profile_for_user(user):
	return Teacher.objects.select_related("account", "account__user").filter(account__user=user).first()


class CourseAccessMixin:
	def _can_manage_all_courses(self):
		user = self.request.user
		return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))

	def _can_manage_owned_courses(self):
		return bool(self._teacher_profile())

	def _student_profile(self):
		return _student_profile_for_user(self.request.user)

	def _teacher_profile(self):
		return _teacher_profile_for_user(self.request.user)

	def _visible_courses_queryset(self):
		queryset = _base_course_queryset()
		if self._can_manage_all_courses():
			return queryset

		teacher_profile = self._teacher_profile()
		if teacher_profile:
			return queryset.filter(teacher=teacher_profile)

		student_profile = self._student_profile()
		if student_profile:
			return queryset.filter(enrollments__student=student_profile).distinct()

		return queryset.none()

	def _visible_lessons_queryset(self):
		return Lesson.objects.select_related(
			"course",
			"course__category",
			"course__teacher",
			"course__teacher__account",
			"course__teacher__account__user",
		).filter(course__in=self._visible_courses_queryset())

	def _visible_schedules_queryset(self):
		return Schedule.objects.select_related(
			"course",
			"course__category",
			"course__teacher",
			"course__teacher__account",
			"course__teacher__account__user",
			"lesson",
		).filter(course__in=self._visible_courses_queryset())

	def _enforce_course_content_management(self):
		if self._can_manage_all_courses() or self._can_manage_owned_courses():
			return
		raise PermissionDenied("Only staff and the owning teacher can manage course content.")


class EnrollmentAccessMixin(CourseAccessMixin):
	def _visible_enrollments_queryset(self):
		queryset = _base_enrollment_queryset()
		if self._can_manage_all_courses():
			return queryset

		teacher_profile = self._teacher_profile()
		if teacher_profile:
			return queryset.filter(course__teacher=teacher_profile)

		student_profile = self._student_profile()
		if student_profile:
			return queryset.filter(student=student_profile)

		return queryset.none()


class CategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Category
	permission_required = "courses.view_category"
	template_name = "courses/category_list.html"
	context_object_name = "categories"
	paginate_by = 25


class CategoryDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Category
	permission_required = "courses.view_category"
	template_name = "courses/category_detail.html"
	context_object_name = "category"


class CategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Category
	form_class = CategoryForm
	permission_required = "courses.add_category"
	template_name = "courses/category_form.html"
	success_url = reverse_lazy("courses:category_list")


class CategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Category
	form_class = CategoryForm
	permission_required = "courses.change_category"
	template_name = "courses/category_form.html"
	success_url = reverse_lazy("courses:category_list")


class CategoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Category
	permission_required = "courses.delete_category"
	template_name = "courses/category_confirm_delete.html"
	success_url = reverse_lazy("courses:category_list")


class CourseListView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Course
	permission_required = "courses.view_course"
	template_name = "courses/course_list.html"
	context_object_name = "courses"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_courses_queryset()


class CourseDetailView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Course
	permission_required = "courses.view_course"
	template_name = "courses/course_detail.html"
	context_object_name = "course"

	def get_queryset(self):
		enrollment_queryset = Enrollment.objects.select_related(
			"student",
			"student__account",
			"student__account__user",
		)
		student_profile = self._student_profile()
		if student_profile and not self._can_manage_all_courses() and not self._teacher_profile():
			enrollment_queryset = enrollment_queryset.filter(student=student_profile)

		return self._visible_courses_queryset().prefetch_related(
			Prefetch("lessons", queryset=Lesson.objects.order_by("order")),
			Prefetch("schedules", queryset=Schedule.objects.order_by("starts_at")),
			Prefetch("enrollments", queryset=enrollment_queryset),
		)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["lessons"] = self.object.lessons.all()
		context["schedules"] = self.object.schedules.all()
		context["enrollments"] = self.object.enrollments.all()
		return context


class CourseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Course
	form_class = CourseForm
	permission_required = "courses.add_course"
	template_name = "courses/course_form.html"
	success_url = reverse_lazy("courses:course_list")


class CourseUpdateView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Course
	form_class = CourseForm
	permission_required = "courses.change_course"
	template_name = "courses/course_form.html"
	success_url = reverse_lazy("courses:course_list")

	def get_queryset(self):
		return self._visible_courses_queryset()


class CourseTeacherAssignView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Course
	form_class = TeacherAssignmentForm
	permission_required = "courses.change_course"
	template_name = "courses/course_assign_teacher.html"
	success_url = reverse_lazy("courses:course_list")

	def get_queryset(self):
		return self._visible_courses_queryset()


class CourseDeleteView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Course
	permission_required = "courses.delete_course"
	template_name = "courses/course_confirm_delete.html"
	success_url = reverse_lazy("courses:course_list")

	def get_queryset(self):
		return self._visible_courses_queryset()


class EnrollmentListView(EnrollmentAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Enrollment
	permission_required = "courses.view_enrollment"
	template_name = "courses/enrollment_list.html"
	context_object_name = "enrollments"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_enrollments_queryset()


class EnrollmentDetailView(EnrollmentAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Enrollment
	permission_required = "courses.view_enrollment"
	template_name = "courses/enrollment_detail.html"
	context_object_name = "enrollment"

	def get_queryset(self):
		return self._visible_enrollments_queryset()


class EnrollmentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Enrollment
	form_class = EnrollmentForm
	permission_required = "courses.add_enrollment"
	template_name = "courses/enrollment_form.html"
	success_url = reverse_lazy("courses:enrollment_list")


class EnrollmentUpdateView(EnrollmentAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Enrollment
	form_class = EnrollmentForm
	permission_required = "courses.change_enrollment"
	template_name = "courses/enrollment_form.html"
	success_url = reverse_lazy("courses:enrollment_list")

	def get_queryset(self):
		return self._visible_enrollments_queryset()


class EnrollmentDeleteView(EnrollmentAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Enrollment
	permission_required = "courses.delete_enrollment"
	template_name = "courses/enrollment_confirm_delete.html"
	success_url = reverse_lazy("courses:enrollment_list")

	def get_queryset(self):
		return self._visible_enrollments_queryset()


class LessonListView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Lesson
	permission_required = "courses.view_lesson"
	template_name = "courses/lesson_list.html"
	context_object_name = "lessons"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_lessons_queryset()


class LessonDetailView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Lesson
	permission_required = "courses.view_lesson"
	template_name = "courses/lesson_detail.html"
	context_object_name = "lesson"

	def get_queryset(self):
		return self._visible_lessons_queryset()


class LessonCreateView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Lesson
	form_class = LessonForm
	permission_required = "courses.add_lesson"
	template_name = "courses/lesson_form.html"
	success_url = reverse_lazy("courses:lesson_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		form.fields["course"].queryset = self._visible_courses_queryset().order_by("code")
		return form

class LessonUpdateView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Lesson
	form_class = LessonForm
	permission_required = "courses.change_lesson"
	template_name = "courses/lesson_form.html"
	success_url = reverse_lazy("courses:lesson_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._visible_lessons_queryset()

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		form.fields["course"].queryset = self._visible_courses_queryset().order_by("code")
		return form


class LessonDeleteView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Lesson
	permission_required = "courses.delete_lesson"
	template_name = "courses/lesson_confirm_delete.html"
	success_url = reverse_lazy("courses:lesson_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._visible_lessons_queryset()


class ScheduleListView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Schedule
	permission_required = "courses.view_schedule"
	template_name = "courses/schedule_list.html"
	context_object_name = "schedules"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_schedules_queryset()


class ScheduleDetailView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Schedule
	permission_required = "courses.view_schedule"
	template_name = "courses/schedule_detail.html"
	context_object_name = "schedule"

	def get_queryset(self):
		return self._visible_schedules_queryset()


class ScheduleCreateView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Schedule
	form_class = ScheduleForm
	permission_required = "courses.add_schedule"
	template_name = "courses/schedule_form.html"
	success_url = reverse_lazy("courses:schedule_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		visible_courses = self._visible_courses_queryset().order_by("code")
		form.fields["course"].queryset = visible_courses
		form.fields["lesson"].queryset = self._visible_lessons_queryset().order_by("course__code", "order", "pk")
		return form

class ScheduleUpdateView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Schedule
	form_class = ScheduleForm
	permission_required = "courses.change_schedule"
	template_name = "courses/schedule_form.html"
	success_url = reverse_lazy("courses:schedule_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._visible_schedules_queryset()

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		form.fields["course"].queryset = self._visible_courses_queryset().order_by("code")
		form.fields["lesson"].queryset = self._visible_lessons_queryset().order_by("course__code", "order", "pk")
		return form


class ScheduleDeleteView(CourseAccessMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Schedule
	permission_required = "courses.delete_schedule"
	template_name = "courses/schedule_confirm_delete.html"
	success_url = reverse_lazy("courses:schedule_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_course_content_management()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._visible_schedules_queryset()


class HomeworkSubmissionAccessMixin:
	def _student_profile(self):
		return Student.objects.select_related("account", "account__user").filter(
			account__user=self.request.user
		).first()

	def _teacher_profile(self):
		return _teacher_profile_for_user(self.request.user)

	def _can_manage_all(self):
		user = self.request.user
		return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))

	def _base_queryset(self):
		return HomeworkSubmission.objects.select_related(
			"enrollment",
			"enrollment__student",
			"enrollment__student__account",
			"enrollment__student__account__user",
			"enrollment__course",
			"lesson",
		)

	def _user_queryset(self):
		queryset = self._base_queryset()
		if self._can_manage_all():
			return queryset

		teacher_profile = self._teacher_profile()
		if teacher_profile:
			return queryset.filter(enrollment__course__teacher=teacher_profile)

		student_profile = self._student_profile()
		if not student_profile:
			return HomeworkSubmission.objects.none()
		return queryset.filter(enrollment__student=student_profile)

	def _visible_enrollments_queryset(self):
		queryset = Enrollment.objects.select_related("course", "student")
		if self._can_manage_all():
			return queryset

		teacher_profile = self._teacher_profile()
		if teacher_profile:
			return queryset.filter(course__teacher=teacher_profile)

		student_profile = self._student_profile()
		if not student_profile:
			return Enrollment.objects.none()
		return queryset.filter(student=student_profile)

	def _visible_lessons_queryset(self):
		queryset = Lesson.objects.select_related("course")
		if self._can_manage_all():
			return queryset

		teacher_profile = self._teacher_profile()
		if teacher_profile:
			return queryset.filter(course__teacher=teacher_profile)

		student_profile = self._student_profile()
		if not student_profile:
			return Lesson.objects.none()
		return queryset.filter(course__enrollments__student=student_profile).distinct()


class HomeworkSubmissionListView(HomeworkSubmissionAccessMixin, LoginRequiredMixin, ListView):
	model = HomeworkSubmission
	template_name = "courses/homeworksubmission_list.html"
	context_object_name = "submissions"
	paginate_by = 25

	def get_queryset(self):
		return self._user_queryset()


class HomeworkSubmissionDetailView(HomeworkSubmissionAccessMixin, LoginRequiredMixin, DetailView):
	model = HomeworkSubmission
	template_name = "courses/homeworksubmission_detail.html"
	context_object_name = "submission"

	def get_queryset(self):
		return self._user_queryset()


class HomeworkSubmissionCreateView(HomeworkSubmissionAccessMixin, LoginRequiredMixin, CreateView):
	model = HomeworkSubmission
	form_class = HomeworkSubmissionForm
	template_name = "courses/homeworksubmission_form.html"
	success_url = reverse_lazy("courses:homework_submission_list")

	def dispatch(self, request, *args, **kwargs):
		if self._can_manage_all():
			return super().dispatch(request, *args, **kwargs)

		if not self._student_profile():
			messages.error(request, "Only student accounts can upload homework.")
			return redirect("home")

		return super().dispatch(request, *args, **kwargs)

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		form.fields["enrollment"].queryset = self._visible_enrollments_queryset().order_by("course__code", "pk")
		form.fields["lesson"].queryset = self._visible_lessons_queryset().order_by("course__code", "order", "pk")
		if not self._can_manage_all() and not self._teacher_profile():
			form.fields["status"].initial = HomeworkSubmission.Status.SUBMITTED
			form.fields["status"].disabled = True
			form.fields["grade"].disabled = True
			form.fields["feedback"].disabled = True
		return form

	def form_valid(self, form):
		if not self._can_manage_all():
			form.instance.status = HomeworkSubmission.Status.SUBMITTED
			form.instance.grade = None
			form.instance.feedback = ""
		return super().form_valid(form)


class HomeworkSubmissionUpdateView(HomeworkSubmissionAccessMixin, LoginRequiredMixin, UpdateView):
	model = HomeworkSubmission
	form_class = HomeworkSubmissionForm
	template_name = "courses/homeworksubmission_form.html"
	success_url = reverse_lazy("courses:homework_submission_list")

	def get_queryset(self):
		return self._user_queryset()

	def get_form(self, form_class=None):
		form = super().get_form(form_class)
		form.fields["enrollment"].queryset = self._visible_enrollments_queryset().order_by("course__code", "pk")
		form.fields["lesson"].queryset = self._visible_lessons_queryset().order_by("course__code", "order", "pk")
		if not self._can_manage_all() and not self._teacher_profile():
			form.fields["status"].disabled = True
			form.fields["grade"].disabled = True
			form.fields["feedback"].disabled = True
		return form


class HomeworkSubmissionDeleteView(HomeworkSubmissionAccessMixin, LoginRequiredMixin, DeleteView):
	model = HomeworkSubmission
	template_name = "courses/homeworksubmission_confirm_delete.html"
	success_url = reverse_lazy("courses:homework_submission_list")

	def get_queryset(self):
		return self._user_queryset()
