from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

from accounts import views as account_views
from dashboard.views import HomePageView

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('healthz/', lambda request: JsonResponse({'status': 'ok'}), name='healthz'),

    path('accounts/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('dashboard/', include(('dashboard.urls', 'dashboard'), namespace='dashboard')),
    path('students/', include(('students.urls', 'students'), namespace='students')),
    path('teachers/', include(('teachers.urls', 'teachers'), namespace='teachers')),
    path('courses/', include(('courses.urls', 'courses'), namespace='courses')),
    path('subscriptions/', include(('subscriptions.urls', 'subscriptions'), namespace='subscriptions')),
    path('payments/', include(('payments.urls', 'payments'), namespace='payments')),
    path('notifications/', include(('notifications.urls', 'notifications'), namespace='notifications')),
    path('exams/', include(('exams.urls', 'exams'), namespace='exams')),

    path('admin-login/', account_views.role_login, {'role_key': 'administrator'}, name='administrator_login'),
    path('teacher-login/', account_views.role_login, {'role_key': 'teacher'}, name='teacher_login'),
    path('student-login/', account_views.role_login, {'role_key': 'student'}, name='student_login'),
    path('parent-login/', account_views.role_login, {'role_key': 'parent'}, name='parent_login'),
    path('logout/', account_views.logout_view, name='logout'),
    path('admin/', account_views.admin_dashboard, name='admin_dashboard'),
    path('teacher/', account_views.teacher_dashboard, name='teacher_dashboard'),
    path('student/', account_views.student_dashboard, name='student_dashboard'),
    path('parent/', account_views.parent_dashboard, name='parent_dashboard'),
    path('profile/photo/', account_views.profile_photo_upload, name='profile_photo_upload'),

    path('', HomePageView.as_view(), name='home'),

    path('identity-settings/', TemplateView.as_view(template_name='identity_settings.html'), name='identity_settings'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)