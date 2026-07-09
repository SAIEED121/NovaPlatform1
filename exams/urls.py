from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
	path("", views.ExamListView.as_view(), name="exam_list"),
	path("results/", views.TeacherResultListView.as_view(), name="result_list"),
	path("reports/", views.TeacherExamReportListView.as_view(), name="report_list"),
	path("results/<int:student_exam_pk>/grade/", views.TeacherEssayGradeView.as_view(), name="result_grade"),
	path("create/", views.ExamCreateView.as_view(), name="exam_create"),
	path("<int:pk>/", views.ExamDetailView.as_view(), name="exam_detail"),
	path("<int:pk>/edit/", views.ExamUpdateView.as_view(), name="exam_update"),
	path("<int:pk>/delete/", views.ExamDeleteView.as_view(), name="exam_delete"),
	path("<int:pk>/publish-toggle/", views.ExamPublishToggleView.as_view(), name="exam_publish_toggle"),
	path("student/", views.StudentExamListView.as_view(), name="student_exam_list"),
	path("student/<int:pk>/", views.StudentExamDetailView.as_view(), name="student_exam_detail"),
	path("student/<int:pk>/result/", views.StudentExamResultView.as_view(), name="student_exam_result"),

	path("<int:exam_pk>/questions/create/", views.QuestionCreateView.as_view(), name="question_create"),
	path("<int:exam_pk>/questions/<int:pk>/edit/", views.QuestionUpdateView.as_view(), name="question_update"),
	path("<int:exam_pk>/questions/<int:pk>/delete/", views.QuestionDeleteView.as_view(), name="question_delete"),

	path(
		"<int:exam_pk>/questions/<int:question_pk>/choices/create/",
		views.ChoiceCreateView.as_view(),
		name="choice_create",
	),
	path(
		"<int:exam_pk>/questions/<int:question_pk>/choices/<int:pk>/edit/",
		views.ChoiceUpdateView.as_view(),
		name="choice_update",
	),
	path(
		"<int:exam_pk>/questions/<int:question_pk>/choices/<int:pk>/delete/",
		views.ChoiceDeleteView.as_view(),
		name="choice_delete",
	),
]
