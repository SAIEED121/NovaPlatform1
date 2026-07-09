from django.urls import path
from . import views

app_name = "courses"

urlpatterns = [
	path("categories/", views.CategoryListView.as_view(), name="category_list"),
	path("categories/create/", views.CategoryCreateView.as_view(), name="category_create"),
	path("categories/<int:pk>/", views.CategoryDetailView.as_view(), name="category_detail"),
	path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
	path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),

	path("", views.CourseListView.as_view(), name="course_list"),
	path("create/", views.CourseCreateView.as_view(), name="course_create"),
	path("<int:pk>/", views.CourseDetailView.as_view(), name="course_detail"),
	path("<int:pk>/edit/", views.CourseUpdateView.as_view(), name="course_update"),
	path("<int:pk>/delete/", views.CourseDeleteView.as_view(), name="course_delete"),
	path("<int:pk>/assign-teacher/", views.CourseTeacherAssignView.as_view(), name="course_assign_teacher"),

	path("enrollments/", views.EnrollmentListView.as_view(), name="enrollment_list"),
	path("enrollments/create/", views.EnrollmentCreateView.as_view(), name="enrollment_create"),
	path("enrollments/<int:pk>/", views.EnrollmentDetailView.as_view(), name="enrollment_detail"),
	path("enrollments/<int:pk>/edit/", views.EnrollmentUpdateView.as_view(), name="enrollment_update"),
	path("enrollments/<int:pk>/delete/", views.EnrollmentDeleteView.as_view(), name="enrollment_delete"),

	path("lessons/", views.LessonListView.as_view(), name="lesson_list"),
	path("lessons/create/", views.LessonCreateView.as_view(), name="lesson_create"),
	path("lessons/<int:pk>/", views.LessonDetailView.as_view(), name="lesson_detail"),
	path("lessons/<int:pk>/edit/", views.LessonUpdateView.as_view(), name="lesson_update"),
	path("lessons/<int:pk>/delete/", views.LessonDeleteView.as_view(), name="lesson_delete"),

	path("schedules/", views.ScheduleListView.as_view(), name="schedule_list"),
	path("schedules/create/", views.ScheduleCreateView.as_view(), name="schedule_create"),
	path("schedules/<int:pk>/", views.ScheduleDetailView.as_view(), name="schedule_detail"),
	path("schedules/<int:pk>/edit/", views.ScheduleUpdateView.as_view(), name="schedule_update"),
	path("schedules/<int:pk>/delete/", views.ScheduleDeleteView.as_view(), name="schedule_delete"),

	path("homework/", views.HomeworkSubmissionListView.as_view(), name="homework_submission_list"),
	path("homework/create/", views.HomeworkSubmissionCreateView.as_view(), name="homework_submission_create"),
	path("homework/<int:pk>/", views.HomeworkSubmissionDetailView.as_view(), name="homework_submission_detail"),
	path("homework/<int:pk>/edit/", views.HomeworkSubmissionUpdateView.as_view(), name="homework_submission_update"),
	path("homework/<int:pk>/delete/", views.HomeworkSubmissionDeleteView.as_view(), name="homework_submission_delete"),
]
