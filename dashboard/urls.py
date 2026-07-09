from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
	path("search/", views.global_search, name="global_search"),
	path("reports/", views.reports_dashboard, name="reports_dashboard"),
]
