# apps/accounting/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    GLAccountViewSet,
    JournalEntryViewSet,
    LoanLossProvisionViewSet,
    trial_balance,
    income_statement,
    balance_sheet,
    npl_return,
    portfolio_at_risk,
)
from .views_bank import (
    BankAccountViewSet,
    BankStatementViewSet,
    BankStatementLineViewSet,
    BankReconciliationViewSet,
    UnmatchedGLLineViewSet,
)
from .views_export import (
    export_trial_balance,
    export_income_statement,
    export_balance_sheet,
    export_npl_return,
    export_par,
)
from . import api_provisioning

router = DefaultRouter()

# Core accounting
router.register(r'accounts', GLAccountViewSet, basename='gl-account')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register(r'provisions', LoanLossProvisionViewSet, basename='loan-loss-provision')

# Bank reconciliation
router.register(r'bank-accounts',         BankAccountViewSet,          basename='bank-account')
router.register(r'bank-statements',       BankStatementViewSet,        basename='bank-statement')
router.register(r'bank-lines',            BankStatementLineViewSet,    basename='bank-statement-line')
router.register(r'bank-reconciliations',  BankReconciliationViewSet,   basename='bank-reconciliation')
router.register(r'unmatched-gl-lines',    UnmatchedGLLineViewSet,      basename='unmatched-gl-line')

urlpatterns = [
    path('', include(router.urls)),

    # Financial statement reports (JSON — read by the UI)
    path('reports/trial-balance/',       trial_balance,       name='trial-balance'),
    path('reports/income-statement/',    income_statement,    name='income-statement'),
    path('reports/balance-sheet/',       balance_sheet,       name='balance-sheet'),
    path('reports/npl-return/',          npl_return,          name='npl-return'),
    path('reports/portfolio-at-risk/',   portfolio_at_risk,   name='portfolio-at-risk'),

    #Non-Performing Loan Calculation and Journal Posting for BOZ Requirement
    path('provisioning/preview/', api_provisioning.provisioning_preview, name='provisioning-preview'),
    path('provisioning/post/',    api_provisioning.provisioning_post,    name='provisioning-post'),

    # Exports (PDF / Excel)
    path('exports/trial-balance/',       export_trial_balance,    name='export-trial-balance'),
    path('exports/income-statement/',    export_income_statement, name='export-income-statement'),
    path('exports/balance-sheet/',       export_balance_sheet,    name='export-balance-sheet'),
    path('exports/npl-return/',          export_npl_return,       name='export-npl-return'),
    path('exports/portfolio-at-risk/',   export_par,              name='export-par'),
]