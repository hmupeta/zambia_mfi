# apps/payroll/urls_pages.py
from django.urls import path
from . import views_pages

urlpatterns = [
    path('payroll/', views_pages.payroll_dashboard, name='payroll-dashboard'),
    path('payroll/runs/', views_pages.payroll_runs_list, name='payroll-runs'),
    path('payroll/runs/create/', views_pages.payroll_run_create, name='payroll-run-create'),
    path('payroll/runs/<uuid:pk>/', views_pages.payroll_run_detail, name='payroll-run-detail'),
]