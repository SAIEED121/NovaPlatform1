from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("plans/", views.SubscriptionPlanListView.as_view(), name="plan_list"),
    path("plans/create/", views.SubscriptionPlanCreateView.as_view(), name="plan_create"),
    path("plans/<int:pk>/", views.SubscriptionPlanDetailView.as_view(), name="plan_detail"),
    path("plans/<int:pk>/edit/", views.SubscriptionPlanUpdateView.as_view(), name="plan_update"),
    path("plans/<int:pk>/delete/", views.SubscriptionPlanDeleteView.as_view(), name="plan_delete"),

    path("plan-courses/", views.PlanCourseListView.as_view(), name="plan_course_list"),
    path("plan-courses/create/", views.PlanCourseCreateView.as_view(), name="plan_course_create"),
    path("plan-courses/<int:pk>/", views.PlanCourseDetailView.as_view(), name="plan_course_detail"),
    path("plan-courses/<int:pk>/edit/", views.PlanCourseUpdateView.as_view(), name="plan_course_update"),
    path("plan-courses/<int:pk>/delete/", views.PlanCourseDeleteView.as_view(), name="plan_course_delete"),

    path("student-subscriptions/", views.StudentSubscriptionListView.as_view(), name="student_subscription_list"),
    path("student-subscriptions/create/", views.StudentSubscriptionCreateView.as_view(), name="student_subscription_create"),
    path("student-subscriptions/<int:pk>/", views.StudentSubscriptionDetailView.as_view(), name="student_subscription_detail"),
    path("student-subscriptions/<int:pk>/edit/", views.StudentSubscriptionUpdateView.as_view(), name="student_subscription_update"),
    path("student-subscriptions/<int:pk>/delete/", views.StudentSubscriptionDeleteView.as_view(), name="student_subscription_delete"),
]
