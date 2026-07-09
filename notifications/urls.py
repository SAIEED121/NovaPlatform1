from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
	path("inbox/", views.NotificationInboxView.as_view(), name="inbox"),
	path("mark-all-read/", views.NotificationMarkAllReadView.as_view(), name="mark_all_read"),
	path("<int:pk>/mark-read/", views.NotificationMarkReadView.as_view(), name="mark_read"),
	path("", views.NotificationListView.as_view(), name="notification_list"),
	path("create/", views.NotificationCreateView.as_view(), name="notification_create"),
	path("<int:pk>/", views.NotificationDetailView.as_view(), name="notification_detail"),
	path("<int:pk>/edit/", views.NotificationUpdateView.as_view(), name="notification_update"),
	path("<int:pk>/delete/", views.NotificationDeleteView.as_view(), name="notification_delete"),
]
