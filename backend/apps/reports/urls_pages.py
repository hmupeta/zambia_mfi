# apps/reports/urls_pages.py
from django.urls import path
from . import views_pages

urlpatterns = [
    path('analytics/', views_pages.analytics_hub, name='analytics-hub-page'),
    path('app/reports/', views_pages.reports_hub, name='ui-reports'),
]