# core/views_auth_ui.py

from django.shortcuts import render, redirect
from django.contrib.auth import logout as django_logout
from django.contrib.auth.decorators import login_required

from .models import LegalDocument, OrganizationAgreement

# ============================================================
# Helpers
# ============================================================
def _ctx(trail, **extra):
    """
    Build a context dict with a standard breadcrumb trail.
    The last item is rendered as the current page (bold, no link).
    """
    ctx = {'breadcrumbs': trail}
    ctx.update(extra)
    return ctx


# ============================================================
# Auth / public
# ============================================================
def login_page(request):
    """Renders the login form. Displays errors passed via ?error=... query string."""
    error_code = request.GET.get('error')
    error_messages = {
        'invalid': 'Invalid username or password.',
        'org_inactive': (
            'Your account is pending verification of your Bank of Zambia licence. '
            'You will be notified by email once your organization has been activated.'
        ),
        'org_suspended': 'Your organization has been suspended. Contact support.',
    }
    return render(request, 'auth/login.html', {
        'page': 'login',
        'error': error_messages.get(error_code, ''),
    })


def signup_page(request):
    return render(request, 'auth/signup.html', {'page': 'signup'})


def forgot_password_page(request):
    return render(request, 'auth/forgot_password.html', {'page': 'forgot'})


def reset_password_page(request):
    return render(request, 'auth/reset_password.html', {'page': 'reset'})


def logout_page(request):
    django_logout(request)
    return redirect('ui-login')


# ============================================================
# Pending verification (post-signup, pre-activation)
# ============================================================
def pending_verification_page(request):
    """
    Shown to a user who successfully signed up but whose organization
    has not yet been activated by a Nimbus admin.
    """
    return render(request, 'auth/pending_verification.html', {'page': 'pending'})


# ============================================================
# Agreement signing (compliance gate)
# ============================================================
@login_required
def sign_agreement_page(request):
    """
    Displays all active Legal Documents the user's org has not yet signed.
    The form POSTs to views_auth.sign_agreement_view.
    """
    org = getattr(request.user, 'organization', None)
    if not org:
        # Platform admins have no org — send them to the dashboard
        return redirect('ui-dashboard')

    active_docs = LegalDocument.objects.filter(is_active=True)
    signed_doc_ids = OrganizationAgreement.objects.filter(
        organization=org, status='SIGNED'
    ).values_list('document_id', flat=True)

    missing_docs = active_docs.exclude(id__in=signed_doc_ids)

    if not missing_docs.exists():
        return redirect('ui-dashboard')

    return render(request, 'auth/sign_agreement.html', {
        'page': 'sign_agreement',
        'documents': missing_docs,
        'organization': org,
        'default_signed_by_name': (
            request.user.get_full_name() or request.user.username
        ),
    })


# ============================================================
# Main
# ============================================================
def app_page(request):
    return redirect('ui-dashboard')


# --- CRITICAL FIX: @login_required REMOVED HERE ---
def dashboard_page(request):
    """
    Renders the main dashboard shell. 
    Authentication and Role-based redirects are handled by JavaScript 
    in base_app.html to prevent infinite redirect loops between 
    Django's Session auth and the frontend's JWT auth.
    """
    return render(request, 'app/dashboard.html')
# --------------------------------------------------


def profile_page(request):
    return render(request, 'app/profile.html', _ctx([
        {'label': 'My Account', 'href': None},
        {'label': 'Profile',    'href': None},
    ]))


def password_change_page(request):
    return render(request, 'app/password_change.html', _ctx([
        {'label': 'My Account',      'href': None},
        {'label': 'Change password', 'href': None},
    ]))


# ============================================================
# Lending
# ============================================================
def applications_list_page(request):
    return render(request, 'app/applications/list.html', _ctx([
        {'label': 'Lending',      'href': None},
        {'label': 'Applications', 'href': None},
    ]))


def application_new_page(request):
    return render(request, 'app/applications/new.html', _ctx([
        {'label': 'Lending',      'href': None},
        {'label': 'Applications', 'href': '/app/applications/'},
        {'label': 'New',          'href': None},
    ]))


def application_detail_page(request, pk):
    return render(request, 'app/applications/detail.html', _ctx([
        {'label': 'Lending',      'href': None},
        {'label': 'Applications', 'href': '/app/applications/'},
        {'label': 'Application',  'href': None},
    ], application_id=str(pk)))


def loans_list_page(request):
    return render(request, 'app/loans/list.html', _ctx([
        {'label': 'Lending', 'href': None},
        {'label': 'Loans',   'href': None},
    ]))


def loan_detail_page(request, pk):
    return render(request, 'app/loans/detail.html', _ctx([
        {'label': 'Lending', 'href': None},
        {'label': 'Loans',   'href': '/app/loans/'},
        {'label': 'Loan',    'href': None},
    ], loan_id=str(pk)))


def payments_list_page(request):
    return render(request, 'app/payments/list.html', _ctx([
        {'label': 'Lending',  'href': None},
        {'label': 'Payments', 'href': None},
    ]))


def payment_new_page(request):
    return render(request, 'app/payments/new.html', _ctx([
        {'label': 'Lending',  'href': None},
        {'label': 'Payments', 'href': '/app/payments/'},
        {'label': 'Record',   'href': None},
    ]))


def payment_detail_page(request, pk):
    return render(request, 'app/payments/detail.html', _ctx([
        {'label': 'Lending',  'href': None},
        {'label': 'Payments', 'href': '/app/payments/'},
        {'label': 'Payment',  'href': None},
    ], payment_id=str(pk)))


def wallets_page(request):
    return render(request, 'app/payments/wallets.html', _ctx([
        {'label': 'Lending',  'href': None},
        {'label': 'Payments', 'href': '/app/payments/'},
        {'label': 'Wallets',  'href': None},
    ]))


def clients_list_page(request):
    return render(request, 'app/clients/list.html', _ctx([
        {'label': 'Lending', 'href': None},
        {'label': 'Clients', 'href': None},
    ]))


def client_detail_page(request, pk):
    return render(request, 'app/clients/detail.html', _ctx([
        {'label': 'Lending', 'href': None},
        {'label': 'Clients', 'href': '/app/clients/'},
        {'label': 'Client',  'href': None},
    ], client_id=str(pk)))


def kyc_queue_page(request):
    return render(request, 'app/kyc/queue.html', _ctx([
        {'label': 'Lending',          'href': None},
        {'label': 'KYC Verification', 'href': None},
    ]))


def kyc_detail_page(request, pk):
    return render(request, 'app/kyc/detail.html', _ctx([
        {'label': 'Lending',          'href': None},
        {'label': 'KYC Verification', 'href': '/app/kyc/'},
        {'label': 'Verification',     'href': None},
    ], verification_id=str(pk)))


# ============================================================
# Accounting
# ============================================================
def gl_accounts_page(request):
    return render(request, 'app/accounting/gl_accounts.html', _ctx([
        {'label': 'Accounting',        'href': None},
        {'label': 'Chart of Accounts', 'href': None},
    ]))


def journal_entries_page(request):
    return render(request, 'app/accounting/journal_entries.html', _ctx([
        {'label': 'Accounting',      'href': None},
        {'label': 'Journal Entries', 'href': None},
    ]))


def journal_entry_detail_page(request, pk):
    return render(request, 'app/accounting/journal_entry_detail.html', _ctx([
        {'label': 'Accounting',      'href': None},
        {'label': 'Journal Entries', 'href': '/app/accounting/journal-entries/'},
        {'label': 'Entry',           'href': None},
    ], entry_id=str(pk)))


def financial_statements_page(request):
    return render(request, 'app/accounting/statements.html', _ctx([
        {'label': 'Accounting',           'href': None},
        {'label': 'Financial Statements', 'href': None},
    ]))


def boz_reports_page(request):
    return render(request, 'app/accounting/boz_reports.html', _ctx([
        {'label': 'Accounting',  'href': None},
        {'label': 'BoZ Reports', 'href': None},
    ]))


def ui_bank_reconciliation(request):
    return render(request, 'app/accounting/bank_reconciliation.html', _ctx([
        {'label': 'Accounting',          'href': None},
        {'label': 'Bank Reconciliation', 'href': None},
    ]))


def ui_executive_dashboard(request):
    return render(request, 'app/accounting/dashboard.html', _ctx([
        {'label': 'Analytics',           'href': None},
        {'label': 'Executive Dashboard', 'href': None},
    ]))


# ============================================================
# Reports
# ============================================================
def ui_reports(request):
    return render(request, 'app/reports/index.html', _ctx([
        {'label': 'Analytics', 'href': None},
        {'label': 'Reports',   'href': None},
    ]))


# ============================================================
# Expenses
# ============================================================
def ui_expenses(request):
    return render(request, 'app/expenses/list.html', _ctx([
        {'label': 'Accounting', 'href': None},
        {'label': 'Expenses',   'href': None},
    ]))


def ui_expense_new(request):
    return render(request, 'app/expenses/new.html', _ctx([
        {'label': 'Accounting', 'href': None},
        {'label': 'Expenses',   'href': '/app/expenses/'},
        {'label': 'New',        'href': None},
    ]))


def ui_expense_detail(request, pk):
    return render(request, 'app/expenses/detail.html', _ctx([
        {'label': 'Accounting', 'href': None},
        {'label': 'Expenses',   'href': '/app/expenses/'},
        {'label': 'Expense',    'href': None},
    ], expense_id=str(pk)))


# ============================================================
# Admin — Settings
# ============================================================
def ui_settings(request):
    return render(request, 'app/settings/index.html', _ctx([
        {'label': 'Admin',    'href': None},
        {'label': 'Settings', 'href': None},
    ]))


# ============================================================
# Admin — Users
# ============================================================
def ui_users(request):
    return render(request, 'app/admin/users.html', _ctx([
        {'label': 'Admin', 'href': None},
        {'label': 'Users', 'href': None},
    ]))


def ui_user_detail(request, pk):
    return render(request, 'app/admin/user_detail.html', _ctx([
        {'label': 'Admin', 'href': None},
        {'label': 'Users', 'href': '/app/users/'},
        {'label': 'User',  'href': None},
    ], user_id=str(pk)))


# ============================================================
# Admin — Branches
# ============================================================
def ui_branches(request):
    return render(request, 'app/admin/branches.html', _ctx([
        {'label': 'Admin',    'href': None},
        {'label': 'Branches', 'href': None},
    ]))


def ui_branch_detail(request, pk):
    return render(request, 'app/admin/branch_detail.html', _ctx([
        {'label': 'Admin',    'href': None},
        {'label': 'Branches', 'href': '/app/branches/'},
        {'label': 'Branch',   'href': None},
    ], branch_id=str(pk)))


def audit_logs_page(request):
    return render(request, 'app/admin/audit_logs.html')


def ui_reports_analytics(request):
    return render(request, 'app/reports/analytics.html', _ctx([
        {'label': 'Analytics', 'href': None},
        {'label': 'Deep Analytics', 'href': None},
    ]))


def ui_field_approvals(request):
    return render(request, 'app/payments/field_approvals.html', _ctx([
        {'label': 'Lending', 'href': None},
        {'label': 'Payments', 'href': '/app/payments/'},
        {'label': 'Field Approvals', 'href': None},
    ]))