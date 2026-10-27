from django.urls import path
from . import views_pages

urlpatterns = [
    path('notifications/', views_pages.notifications_list, name='notifications-list-page'),
    path('notifications/templates/', views_pages.notifications_templates, name='notifications-templates-page'),
    path('notifications/settings/', views_pages.notifications_settings, name='notifications-settings-page'),
]
