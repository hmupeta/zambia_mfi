#!/usr/bin/env python3
"""
Installer for the Phase AB test suite.
Run from the backend/ directory:   python install_tests.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
GH   = ROOT.parent / ".github" / "workflows"

FILES = []
def add(path, content):
    FILES.append((path, content))

# ═════════════════════════════════════════════
# pytest.ini
# ═════════════════════════════════════════════
add(ROOT / "pytest.ini", r"""[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py tests_*.py
python_classes = Test*
python_functions = test_*
testpaths = apps
addopts =
    --strict-markers
    --tb=short
    --disable-warnings
    -p no:cacheprovider
    --cov=apps
    --cov-report=term-missing:skip-covered
    --cov-report=html:htmlcov
    --cov-fail-under=0
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests that hit the full stack
""")

# ═════════════════════════════════════════════
# conftest.py — root-level fixtures
# ═════════════════════════════════════════════
add(ROOT / "conftest.py", r'''"""
Shared pytest fixtures for the Zambia MFI test suite.

Provides factory-style builders for the core models so individual tests
can focus on the logic under test, not on setup.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import Organization, Branch


User = get_user_model()


# ============================================================
# Organization / Branch / User
# ============================================================
@pytest.fixture
def org(db):
    return Organization.objects.create(
        code='TEST',
        name='Test MFI Ltd',
        email='test@mfi.zm',
        phone='+260971000000',
    )


@pytest.fixture
def branch(db, org):
    return Branch.objects.create(
        organization=org,
        code='HQ-001',
        name='Head Office',
    )


@pytest.fixture
def hq_admin(db, org, branch):
    return User.objects.create_user(
        username='admin@test.mfi',
        email='admin@test.mfi',
        password='test1234!',
        first_name='Admin',
        last_name='User',
        role='HQ_ADMIN',
        organization=org,
        branch=branch,
    )


@pytest.fixture
def branch_manager(db, org, branch):
    return User.objects.create_user(
        username='bm@test.mfi',
        email='bm@test.mfi',
        password='test1234!',
        first_name='Branch',
        last_name='Manager',
        role='BRANCH_MANAGER',
        organization=org,
        branch=branch,
    )


@pytest.fixture
def loan_officer(db, org, branch):
    return User.objects.create_user(
        username='lo@test.mfi',
        email='lo@test.mfi',
        password='test1234!',
        first_name='Loan',
        last_name='Officer',
        role='LOAN_OFFICER',
        organization=org,
        branch=branch,
    )


# ============================================================
# Client
# ============================================================
@pytest.fixture
def client(db, org, branch, hq_admin):
    from apps.clients.models import Client
    return Client.objects.create(
        organization=org,
        branch=branch,
        nrc='123456/11/1',
        first_name='John',
        last_name='Doe',
        gender='M',
        phone='0971234567',
        email='john@example.com',
        kyc_status='VERIFIED',
        created_by=hq_admin,
    )


# ============================================================
# Loan product + loan
# ============================================================
@pytest.fixture
def loan_product(db, org):
    from apps.loans.models import LoanProduct
    return LoanProduct.objects.create(
        organization=org,
        code='AGRI-01',
        name='Agricultural Loan',
        min_amount=Decimal('500'),
        max_amount=Decimal('50000'),
        min_tenure_months=1,
        max_tenure_months=36,
        interest_method='FLAT',
        interest_rate=Decimal('24.00'),
        penalty_rate=Decimal('2.00'),
        repayment_frequency='MONTHLY',
    )


@pytest.fixture
def loan(db, org, branch, client, loan_product, hq_admin):
    """A disbursed loan with 3 installments."""
    from apps.loans.models import Loan, LoanInstallment

    today = date.today()
    principal = Decimal('10000.00')
    interest = Decimal('2400.00')  # 24% flat on 12 months
    total = principal + interest

    loan = Loan.objects.create(
        organization=org,
        branch=branch,
        client=client,
        loan_product=loan_product,
        loan_officer=hq_admin,
        approved_by=hq_admin,
        loan_number='LN-TEST-0001',
        amount=principal,
        total_interest=interest,
        total_amount_due=total,
        disbursed_amount=principal,
        balance_due=total,
        start_date=today,
        maturity_date=today + timedelta(days=365),
        interest_rate=Decimal('24.00'),
        interest_method='FLAT',
        repayment_frequency='MONTHLY',
        status='DISBURSED',
    )

    # Create 3 installments
    monthly = total / 3
    for i in range(1, 4):
        LoanInstallment.objects.create(
            loan=loan,
            installment_no=i,
            due_date=today + timedelta(days=30 * i),
            principal_amount=principal / 3,
            interest_amount=interest / 3,
            penalty_amount=Decimal('0'),
            total_due=monthly,
            paid_amount=Decimal('0'),
            is_paid=False,
            status='PENDING',
        )

    return loan


# ============================================================
# GL accounts — needed for GL posting tests
# ============================================================
@pytest.fixture
def gl_accounts(db, org):
    from apps.accounting.models import GLAccount
    accounts = {}
    specs = [
        ('1010', 'Cash on Hand', 'ASSET', True),
        ('1020', 'Bank Account', 'ASSET', True),
        ('1030', 'Mobile Money', 'ASSET', True),
        ('1100', 'Loans Receivable', 'ASSET', True),
        ('4000', 'Interest Income', 'INCOME', False),
        ('4100', 'Penalty Income', 'INCOME', False),
    ]
    for code, name, atype, debit_normal in specs:
        accounts[code] = GLAccount.objects.create(
            organization=org,
            code=code,
            name=name,
            account_type=atype,
            is_debit_normal=debit_normal,
            is_active=True,
        )
    return accounts


# ============================================================
# API client
# ============================================================
@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def auth_client(api_client, hq_admin):
    """APIClient authenticated as an HQ admin."""
    from rest_framework_simplejwt.tokens import RefreshToken
    token = str(RefreshToken.for_user(hq_admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
    return api_client
''')

# ═════════════════════════════════════════════
# test_payment_allocation.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "payments" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "payments" / "tests" / "test_payment_allocation.py", r'''"""Tests for the payment allocation engine (penalty -> interest -> principal)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.payments.services_admin import preview_allocation, _remaining_breakdown


pytestmark = pytest.mark.django_db


def test_preview_allocation_orders_penalty_first(loan):
    """Payment should be applied to penalties first, then interest, then principal."""
    # Set penalties on the first installment
    inst1 = loan.installments.order_by('installment_no').first()
    inst1.penalty_amount = Decimal('500.00')
    inst1.total_due = inst1.total_due + Decimal('500.00')
    inst1.save()

    plan = preview_allocation(loan, Decimal('500.00'))['plan']
    assert len(plan) >= 1
    row = plan[0]
    assert row['penalty'] == 500.0
    assert row['interest'] == 0
    assert row['principal'] == 0


def test_preview_allocation_waterfall(loan):
    """With a larger payment, we exhaust penalty, then interest, then principal."""
    inst1 = loan.installments.order_by('installment_no').first()
    inst1.penalty_amount = Decimal('100.00')
    inst1.total_due = inst1.total_due + Decimal('100.00')
    inst1.save()

    # Payment covers penalty + interest portion of first installment
    plan = preview_allocation(loan, Decimal('1000.00'))['plan']
    row = plan[0]
    assert row['penalty'] == 100.0
    assert row['interest'] > 0  # spilled into interest
    assert row['subtotal'] > 0


def test_preview_allocation_zero_returns_empty(loan):
    plan = preview_allocation(loan, Decimal('0.00'))['plan']
    assert plan == []


def test_remaining_breakdown_fully_paid(loan):
    inst = loan.installments.first()
    inst.paid_amount = inst.total_due
    inst.save()
    bd = _remaining_breakdown(inst)
    assert bd['total'] == Decimal('0')
''')

# ═════════════════════════════════════════════
# test_payment_gl.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "payments" / "tests" / "test_payment_gl.py", r'''"""Tests for payment GL posting and reversal."""
from decimal import Decimal

import pytest

from apps.payments.services_admin import record_payment
from apps.accounting.models import JournalEntry


pytestmark = pytest.mark.django_db


def test_record_payment_posts_balanced_je(loan, hq_admin, gl_accounts):
    """A payment should create a JE with balanced debits and credits."""
    payment, allocated = record_payment(
        loan=loan,
        amount=Decimal('1000.00'),
        user=hq_admin,
        payment_method='CASH',
    )

    assert payment.journal_entry is not None
    je = payment.journal_entry
    total_debit = sum(line.debit for line in je.lines.all())
    total_credit = sum(line.credit for line in je.lines.all())
    assert total_debit == total_credit == Decimal('1000.00')


def test_record_payment_updates_loan_balance(loan, hq_admin, gl_accounts):
    before = loan.balance_due
    payment, allocated = record_payment(
        loan=loan, amount=Decimal('1000.00'), user=hq_admin,
    )
    loan.refresh_from_db()
    assert loan.balance_due == before - Decimal('1000.00')


def test_record_payment_marks_installment_paid_when_fully_covered(loan, hq_admin, gl_accounts):
    inst = loan.installments.order_by('installment_no').first()
    # Pay exactly what's due on installment 1
    record_payment(loan=loan, amount=inst.total_due, user=hq_admin)
    inst.refresh_from_db()
    assert inst.is_paid is True
    assert inst.status == 'PAID'
''')

# ═════════════════════════════════════════════
# test_loan_disbursement.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "loans" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "loans" / "tests" / "test_loan_disbursement.py", r'''"""Tests for loan disbursement via the admin viewset action."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.loans.models import Loan
from apps.payments.models import BranchWallet


pytestmark = pytest.mark.django_db


@pytest.fixture
def approved_loan(db, loan):
    """Set the loan up in APPROVED state for disbursement."""
    loan.status = 'APPROVED'
    loan.save(update_fields=['status'])
    return loan


def test_disburse_requires_authentication(approved_loan):
    client = APIClient()
    r = client.post(f'/api/loans/admin/{approved_loan.id}/disburse/', {})
    assert r.status_code == 401


def test_disburse_posts_journal_entry(approved_loan, hq_admin, gl_accounts):
    client = APIClient()
    token = str(RefreshToken.for_user(hq_admin).access_token)
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    r = client.post(
        f'/api/loans/admin/{approved_loan.id}/disburse/',
        {'channel': 'BANK', 'reference': 'TEST-REF'},
        format='json',
    )
    assert r.status_code == 200, r.content
    approved_loan.refresh_from_db()
    assert approved_loan.status == 'DISBURSED'
    assert approved_loan.disbursement_journal_entry is not None
    assert approved_loan.disbursement_channel == 'BANK'


def test_disburse_updates_branch_wallet(approved_loan, hq_admin, gl_accounts):
    client = APIClient()
    token = str(RefreshToken.for_user(hq_admin).access_token)
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    client.post(
        f'/api/loans/admin/{approved_loan.id}/disburse/',
        {'channel': 'CASH'},
        format='json',
    )
    wallet = BranchWallet.objects.filter(branch=approved_loan.branch).first()
    assert wallet is not None
    # Cash was used to disburse — cash balance should be negative
    assert wallet.cash_balance == -approved_loan.amount
''')

# ═════════════════════════════════════════════
# test_wallet_service.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "payments" / "tests" / "test_wallet_service.py", r'''"""Tests for wallet balance tracking and reconciliation."""
from decimal import Decimal

import pytest

from apps.payments.services_wallet import WalletService
from apps.payments.models import BranchWallet, WalletTransaction, WalletReconciliation


pytestmark = pytest.mark.django_db


def test_record_movement_increases_balance(branch, hq_admin):
    WalletService.record_movement(
        branch=branch, channel='CASH', amount=Decimal('500'),
        direction='IN', reference='TEST-1', user=hq_admin,
    )
    w = BranchWallet.objects.get(branch=branch)
    assert w.cash_balance == Decimal('500')


def test_record_movement_out_decreases_balance(branch, hq_admin):
    WalletService.record_movement(branch, 'CASH', Decimal('300'), 'IN', user=hq_admin)
    WalletService.record_movement(branch, 'CASH', Decimal('100'), 'OUT', user=hq_admin)
    w = BranchWallet.objects.get(branch=branch)
    assert w.cash_balance == Decimal('200')


def test_record_movement_logs_transaction(branch, hq_admin):
    WalletService.record_movement(
        branch, 'BANK', Decimal('1000'), 'IN', reference='PAY-1', user=hq_admin,
    )
    txn = WalletTransaction.objects.filter(branch=branch).first()
    assert txn is not None
    assert txn.amount == Decimal('1000')
    assert txn.transaction_type == 'LOAN_COLLECTION'


def test_reconcile_balanced(branch, hq_admin):
    WalletService.record_movement(branch, 'CASH', Decimal('1000'), 'IN', user=hq_admin)
    recon = WalletService.reconcile(
        branch, physical_cash=Decimal('1000'),
        physical_momo=Decimal('0'), physical_bank=Decimal('0'),
        notes='Test', user=hq_admin,
    )
    assert recon.status == 'BALANCED'
    assert recon.variance_total == Decimal('0')


def test_reconcile_variance_detected(branch, hq_admin):
    WalletService.record_movement(branch, 'CASH', Decimal('1000'), 'IN', user=hq_admin)
    recon = WalletService.reconcile(
        branch, physical_cash=Decimal('950'),
        physical_momo=Decimal('0'), physical_bank=Decimal('0'),
        notes='Cash missing', user=hq_admin,
    )
    assert recon.status == 'VARIANCE'
    assert recon.variance_total == Decimal('-50')
    assert recon.variance_cash == Decimal('-50')
''')

# ═════════════════════════════════════════════
# test_origination_workflow.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "origination" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "origination" / "tests" / "test_origination_workflow.py", r'''"""Tests for the loan application state machine."""
from decimal import Decimal
from datetime import date

import pytest

from apps.origination.models import (
    LoanApplication, WorkflowTemplate, WorkflowStage,
)
from apps.origination.services import ApplicationService, CreditScoringService


pytestmark = pytest.mark.django_db


@pytest.fixture
def workflow(db, org, loan_product):
    tpl = WorkflowTemplate.objects.create(
        organization=org, name='Standard', is_active=True, is_default=True,
    )
    WorkflowStage.objects.create(
        template=tpl, order=1, name='Review', role_required='LOAN_OFFICER',
        sla_hours=24,
    )
    WorkflowStage.objects.create(
        template=tpl, order=2, name='Approve', role_required='BRANCH_MANAGER',
        sla_hours=24, is_final=True,
    )
    return tpl


@pytest.fixture
def application(db, org, branch, client, loan_product, hq_admin, workflow):
    return LoanApplication.objects.create(
        organization=org, branch=branch, client=client,
        loan_product=loan_product,
        application_number='APP-TEST-0001',
        requested_amount=Decimal('10000'),
        requested_tenure_months=12,
        requested_repayment_frequency='MONTHLY',
        purpose='BUSINESS_CAPITAL',
        status='DRAFT',
        created_by=hq_admin,
        loan_officer=hq_admin,
    )


def test_credit_score_returns_grade(application):
    score, grade = CreditScoringService.score(application)
    assert 0 <= score <= 100
    assert grade in ('A', 'B', 'C', 'D')


def test_submit_moves_to_submitted(application, hq_admin):
    ApplicationService.submit(application, hq_admin)
    application.refresh_from_db()
    assert application.status == 'SUBMITTED'
    assert application.current_stage is not None


def test_advance_requires_different_user(application, hq_admin, branch_manager):
    ApplicationService.submit(application, hq_admin)
    # First user advances — should fail, they just submitted
    with pytest.raises(ValueError, match='already performed the last action'):
        ApplicationService.advance(application, hq_admin)


def test_advance_to_final_stage_approves(application, hq_admin, branch_manager, loan_officer):
    ApplicationService.submit(application, hq_admin)
    # Different user advances
    ApplicationService.advance(application, loan_officer)
    application.refresh_from_db()
    assert application.status == 'UNDER_REVIEW'
    # Branch manager approves at final stage
    ApplicationService.advance(application, branch_manager)
    application.refresh_from_db()
    assert application.status == 'APPROVED'
    assert application.loan is not None
''')

# ═════════════════════════════════════════════
# test_kyc_service.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "kyc" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "kyc" / "tests" / "test_kyc_service.py", r'''"""Tests for KYC risk scoring and verification lifecycle."""
from decimal import Decimal

import pytest

from apps.kyc.services import KYCRiskService, KYCVerificationService


pytestmark = pytest.mark.django_db


def test_risk_score_low_for_rural_client(client, db):
    client.province = 'NORTHERN'
    client.occupation = 'FARMER'
    client.save()
    result = KYCRiskService.compute(client)
    assert result['risk_level'] in ('LOW', 'MEDIUM')


def test_risk_score_high_for_urban_high_risk(client):
    client.province = 'LUSAKA'
    client.occupation = 'MONEY EXCHANGE'
    client.save()
    result = KYCRiskService.compute(client)
    assert result['risk_score'] > 0


def test_initiate_creates_verification(client, hq_admin):
    v = KYCVerificationService.initiate(client, user=hq_admin)
    assert v.status == 'IN_PROGRESS'
    assert v.verification_number.startswith('KYC-')


def test_verify_marks_client_verified(client, hq_admin):
    v = KYCVerificationService.initiate(client, user=hq_admin)
    v.status = 'PENDING_REVIEW'
    v.save()
    KYCVerificationService.verify(v, hq_admin, notes='All checks passed')
    client.refresh_from_db()
    assert client.kyc_status == 'VERIFIED'
''')

# ═════════════════════════════════════════════
# test_notifications.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "notifications" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "notifications" / "tests" / "test_notifications.py", r'''"""Tests for notification services — template rendering, phone normalization."""
from decimal import Decimal

import pytest

from apps.notifications.services import (
    render_template, normalize_phone, send_from_template,
)
from apps.notifications.models import NotificationTemplate, NotificationLog


pytestmark = pytest.mark.django_db


def test_normalize_phone_zambian_local():
    assert normalize_phone('0971234567') == '260971234567'


def test_normalize_phone_with_plus():
    assert normalize_phone('+260971234567') == '260971234567'


def test_normalize_phone_already_has_country_code():
    assert normalize_phone('260971234567') == '260971234567'


def test_normalize_phone_empty():
    assert normalize_phone('') == ''


def test_render_template_basic():
    body = 'Dear {{client_name}}, your balance is K{{balance_due}}.'
    out = render_template(body, {'client_name': 'John', 'balance_due': Decimal('500.00')})
    assert 'John' in out
    assert '500.00' in out


def test_render_template_missing_key_becomes_empty():
    body = 'Hello {{missing_key}}'
    out = render_template(body, {})
    assert 'Hello' in out
    assert '{{' not in out


def test_render_template_decimal_formatted(org):
    body = 'Amount: {{amount}}'
    out = render_template(body, {'amount': Decimal('1234.5678')})
    assert '1,234.57' in out


def test_send_from_template_creates_log(client, org, hq_admin, db):
    NotificationTemplate.objects.create(
        organization=org, key='test_hello', name='Hello', channel='SMS',
        body='Hi {{client_name}}', is_active=True,
    )
    logs = send_from_template(org, client, 'test_hello', sent_by=hq_admin)
    assert len(logs) == 1
    assert NotificationLog.objects.filter(client=client).exists()


def test_send_missing_template_returns_empty(client, org, db):
    logs = send_from_template(org, client, 'no_such_template')
    assert logs == []
''')

# ═════════════════════════════════════════════
# test_documents.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "reports" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "reports" / "tests" / "test_documents.py", r'''"""Tests for printable document helpers."""
from decimal import Decimal

import pytest

from apps.reports.documents import amount_in_words, _sanitize


def test_amount_in_words_zero():
    assert 'Zero' in amount_in_words(Decimal('0'))


def test_amount_in_words_whole_kwacha():
    result = amount_in_words(Decimal('1000'))
    assert 'One Thousand Kwacha' in result
    assert 'Only' in result


def test_amount_in_words_with_ngwee():
    result = amount_in_words(Decimal('1234.56'))
    assert 'One Thousand' in result
    assert 'Ngwee' in result


def test_amount_in_words_complex():
    result = amount_in_words(Decimal('10000'))
    assert 'Ten Thousand Kwacha' in result


def test_sanitize_handles_none():
    assert _sanitize(None) == ''


def test_sanitize_replaces_em_dash():
    assert '--' in _sanitize('Hello \u2014 World')


def test_sanitize_replaces_curly_quotes():
    out = _sanitize('\u2018Hello\u2019 \u201CWorld\u201D')
    assert "'Hello'" in out
    assert '"World"' in out
''')

# ═════════════════════════════════════════════
# test_api_smoke.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "core" / "tests" / "__init__.py", "")
add(ROOT / "apps" / "core" / "tests" / "test_api_smoke.py", r'''"""Smoke tests — endpoints reject unauthenticated requests."""
import pytest
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db


ENDPOINTS = [
    '/api/reports/dashboard/',
    '/api/reports/daily-trend/',
    '/api/reports/analytics/overview/',
    '/api/reports/analytics/aging/',
    '/api/reports/analytics/portfolio-movement/',
    '/api/reports/analytics/interest-income/',
    '/api/reports/analytics/new-vs-repeat/',
    '/api/reports/analytics/loan-officers/',
    '/api/payments/wallets/',
    '/api/payments/wallets/stats/',
    '/api/notifications/logs/',
    '/api/notifications/templates/',
    '/api/clients/',
    '/api/loans/admin/',
    '/api/origination/applications/',
]


@pytest.mark.parametrize('url', ENDPOINTS)
def test_endpoint_requires_auth(url):
    client = APIClient()
    r = client.get(url)
    assert r.status_code == 401, f'{url} returned {r.status_code}, expected 401'


@pytest.mark.parametrize('url', ENDPOINTS[:5])
def test_endpoint_returns_200_when_authed(url, auth_client):
    r = auth_client.get(url)
    assert r.status_code in (200, 201), f'{url} returned {r.status_code}'
''')

# ═════════════════════════════════════════════
# test_analytics.py
# ═════════════════════════════════════════════
add(ROOT / "apps" / "reports" / "tests" / "test_analytics.py", r'''"""Tests for analytics calculations."""
from datetime import date
from decimal import Decimal

import pytest

from apps.reports.services_analytics import (
    aging_analysis, loan_officer_performance, new_vs_repeat_clients,
)


pytestmark = pytest.mark.django_db


def test_aging_analysis_returns_buckets(org, loan):
    result = aging_analysis(org, date.today())
    assert 'rows' in result
    assert len(result['rows']) == 5
    bucket_keys = [r['bucket'] for r in result['rows']]
    assert 'current' in bucket_keys
    assert 'par_90_plus' in bucket_keys


def test_aging_totals_match_row_sum(org, loan):
    result = aging_analysis(org, date.today())
    row_sum = sum(r['outstanding'] for r in result['rows'])
    assert abs(row_sum - result['total_outstanding']) < 0.01


def test_loan_officer_performance_returns_officers(org, loan, hq_admin):
    today = date.today()
    from_m = today.replace(day=1)
    result = loan_officer_performance(org, from_m, today)
    assert 'officers' in result
    assert isinstance(result['officers'], list)


def test_new_vs_repeat_returns_series(org, loan, client):
    result = new_vs_repeat_clients(org, months=3)
    assert 'series' in result
    assert len(result['series']) == 3
    assert all('new' in s and 'repeat' in s for s in result['series'])
''')

# ═════════════════════════════════════════════
# GitHub Actions workflow
# ═════════════════════════════════════════════
add(GH / "test.yml", r'''name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_mfi
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
          cache: pip

      - name: Install dependencies
        working-directory: ./backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run Django checks
        working-directory: ./backend
        env:
          DJANGO_ENV: dev
          DATABASE_URL: postgres://test:test@localhost:5432/test_mfi
          SECRET_KEY: ci-test-key-not-for-production-use-only-50chars
        run: python manage.py check

      - name: Run tests
        working-directory: ./backend
        env:
          DJANGO_ENV: dev
          DATABASE_URL: postgres://test:test@localhost:5432/test_mfi
          SECRET_KEY: ci-test-key-not-for-production-use-only-50chars
        run: pytest -v

      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: backend/htmlcov
          retention-days: 14
''')

# ═════════════════════════════════════════════
# Write
# ═════════════════════════════════════════════
def main():
    print("Writing test suite files...")
    for path, content in FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        try:
            rel = path.relative_to(ROOT.parent)
        except ValueError:
            rel = path
        print(f"  + {rel}")
    print(f"\nDone. {len(FILES)} files written.")
    print("\nNext steps:")
    print("  1. pip install pytest pytest-django pytest-cov factory-boy freezegun")
    print("  2. python manage.py migrate")
    print("  3. pytest -v")
    print("  4. pytest --cov=apps --cov-report=html")


if __name__ == "__main__":
    main()