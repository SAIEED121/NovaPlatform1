from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
	path("login/admin/", views.role_login, {"role_key": "administrator"}, name="administrator_login"),
	path("login/teacher/", views.role_login, {"role_key": "teacher"}, name="teacher_login"),
	path("login/student/", views.role_login, {"role_key": "student"}, name="student_login"),
	path("login/parent/", views.role_login, {"role_key": "parent"}, name="parent_login"),
	path("logout/", views.logout_view, name="logout"),
	path("dashboard/admin/", views.admin_dashboard, name="admin_dashboard"),
	path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
	path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
	path("dashboard/parent/", views.parent_dashboard, name="parent_dashboard"),
	path("profiles/", views.AccountProfileListView.as_view(), name="profile_list"),
	path("profiles/create/", views.AccountProfileCreateView.as_view(), name="profile_create"),
	path("profiles/<int:pk>/", views.AccountProfileDetailView.as_view(), name="profile_detail"),
	path("profiles/<int:pk>/edit/", views.AccountProfileUpdateView.as_view(), name="profile_update"),
	path("profiles/<int:pk>/delete/", views.AccountProfileDeleteView.as_view(), name="profile_delete"),
	path("activity-logs/", views.ActivityLogListView.as_view(), name="activity_log_list"),
	path("activity-logs/export/csv/", views.ActivityLogExportCsvView.as_view(), name="activity_log_export_csv"),
	path("activity-logs/export/excel/", views.ActivityLogExportExcelView.as_view(), name="activity_log_export_excel"),
	path("profile/photo/", views.profile_photo_upload, name="profile_photo_upload"),
]
