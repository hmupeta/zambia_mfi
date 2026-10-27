# apps/payroll/urls_pages.py
from django.urls import path
from . import views_pages

urlpatterns = [
    # Dashboard & Runs
    path('payroll/', views_pages.payroll_dashboard, name='payroll-dashboard'),
    path('payroll/runs/', views_pages.payroll_runs_list, name='payroll-runs'),
    path('payroll/runs/create/', views_pages.payroll_run_create, name='payroll-run-create'),
    path('payroll/runs/<uuid:pk>/', views_pages.payroll_run_detail, name='payroll-run-detail'),
    
    # NEW: Bank File Download
    path('payroll/runs/<uuid:pk>/bank-file/', views_pages.download_bank_file, name='payroll-bank-file'),
    
    # NEW: Payroll Periods
    path('payroll/periods/', views_pages.payroll_periods_list, name='payroll-periods'),
    
    # NEW: GL & Payroll Settings
    path('payroll/settings/', views_pages.payroll_settings, name='payroll-settings'),
]