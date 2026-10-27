"""
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
    """Create the minimum GL accounts needed for GL posting tests."""
    from apps.accounting.models import GLAccount
    accounts = {}
    specs = [
        ('1010', 'Cash on Hand', 'ASSET'),
        ('1020', 'Bank Account', 'ASSET'),
        ('1030', 'Mobile Money', 'ASSET'),
        ('1100', 'Loans Receivable', 'ASSET'),
        ('4000', 'Interest Income', 'INCOME'),
        ('4100', 'Penalty Income', 'INCOME'),
    ]
    for code, name, atype in specs:
        accounts[code] = GLAccount.objects.create(
            organization=org,
            code=code,
            name=name,
            account_type=atype,
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
