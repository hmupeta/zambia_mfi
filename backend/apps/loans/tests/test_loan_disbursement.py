"""Tests for loan disbursement via the admin viewset action."""
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
