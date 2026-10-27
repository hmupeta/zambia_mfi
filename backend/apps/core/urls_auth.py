from django.urls import path
from .views_auth_ui import (
    login_page, signup_page, forgot_password_page, reset_password_page,
    logout_page, app_page, dashboard_page, profile_page, password_change_page,
    applications_list_page, application_detail_page, application_new_page, 
    loans_list_page, loan_detail_page,
    payments_list_page, wallets_page, 
    clients_list_page, client_detail_page,
    kyc_queue_page, kyc_detail_page,
    gl_accounts_page, journal_entries_page, journal_entry_detail_page,
    financial_statements_page, boz_reports_page,
    ui_bank_reconciliation, 
    audit_logs_page,
    ui_reports_analytics           
)
from .views_signup import signup

urlpatterns = [
    path('login/',            login_page,           name='ui-login'),
    path('signup/',           signup_page,          name='ui-signup'),
    path('forgot-password/',  forgot_password_page, name='ui-forgot'),
    path('reset-password/',   reset_password_page,  name='ui-reset'),
    path('logout/',           logout_page,          name='ui-logout'),

    path('app/',                    app_page,             name='ui-app'),
    path('app/dashboard/',          dashboard_page,       name='ui-dashboard'),
    path('app/profile/',            profile_page,         name='ui-profile'),
    path('app/password-change/',    password_change_page, name='ui-password-change'),

    path('app/applications/',             applications_list_page,    name='ui-applications'),
    path('app/applications/new/',         application_new_page,      name='ui-application-new'),
    path('app/applications/<uuid:pk>/',   application_detail_page,   name='ui-application-detail'),

     # ---- Loans ----
    path('app/loans/',          loans_list_page,  name='ui-loans'),
    path('app/loans/<uuid:pk>/', loan_detail_page, name='ui-loan-detail'),

    # ---- Payments ----
    path('app/payments/',         payments_list_page, name='ui-payments'),
    path('app/wallets/',          wallets_page,       name='ui-wallets'),

    # ---- Clients ----
    path('app/clients/',          clients_list_page,  name='ui-clients'),
    path('app/clients/<uuid:pk>/', client_detail_page, name='ui-client-detail'),

     # ---- KYC ----
    path('app/kyc/',                     kyc_queue_page,  name='ui-kyc-queue'),
    path('app/kyc/<uuid:pk>/',           kyc_detail_page, name='ui-kyc-detail'),

        # ---- Accounting ----
    path('app/accounting/',                    gl_accounts_page,           name='ui-gl-accounts'),
    path('app/accounting/journal-entries/',    journal_entries_page,       name='ui-journal-entries'),
    path('app/accounting/journal-entries/<uuid:pk>/', journal_entry_detail_page, name='ui-journal-entry-detail'),
    path('app/accounting/statements/',         financial_statements_page,  name='ui-statements'),
    path('app/accounting/boz-reports/',        boz_reports_page,           name='ui-boz-reports'),
    path('app/accounting/bank-reconciliation/', ui_bank_reconciliation, name='ui-bank-reconciliation'),

    path('api/signup/', signup, name='api-signup'),
    path('app/admin/audit-logs/', audit_logs_page, name='ui-audit-logs'),
    path('app/reports/analytics/', ui_reports_analytics, name='ui-reports-analytics'),
]