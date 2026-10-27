"""Tests for payment reversal — loan restoration and contra-JE posting."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.payments.services_admin import record_payment
from apps.accounting.models import JournalEntry


pytestmark = pytest.mark.django_db


def _reverse(api_client, payment_id, hq_admin, reason='Test reversal'):
    token = str(RefreshToken.for_user(hq_admin).access_token)
    api_client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
    return api_client.post(
        f'/api/payments/admin/{payment_id}/reverse/',
        {'reason': reason},
        format='json',
    )


def test_reversal_restores_loan_balance(loan, hq_admin, gl_accounts, api_client):
    before = loan.balance_due
    payment, _ = record_payment(
        loan=loan, amount=Decimal('1000.00'), user=hq_admin,
        payment_method='CASH',
    )
    loan.refresh_from_db()
    assert loan.balance_due == before - Decimal('1000.00')

    r = _reverse(api_client, payment.id, hq_admin)
    assert r.status_code == 200, r.content

    loan.refresh_from_db()
    assert loan.balance_due == before


def test_reversal_creates_contra_je(loan, hq_admin, gl_accounts, api_client):
    payment, _ = record_payment(
        loan=loan, amount=Decimal('500.00'), user=hq_admin,
        payment_method='CASH',
    )
    original_je_id = payment.journal_entry_id
    assert original_je_id is not None

    je_count_before = JournalEntry.objects.count()
    r = _reverse(api_client, payment.id, hq_admin)
    assert r.status_code == 200

    # A new JE should have been created for the reversal
    assert JournalEntry.objects.count() == je_count_before + 1
    payment.refresh_from_db()
    assert payment.is_reversed is True


def test_reversal_unmarks_installments(loan, hq_admin, gl_accounts, api_client):
    inst = loan.installments.order_by('installment_no').first()
    payment, _ = record_payment(
        loan=loan, amount=inst.total_due, user=hq_admin,
        payment_method='CASH',
    )
    inst.refresh_from_db()
    assert inst.is_paid is True

    _reverse(api_client, payment.id, hq_admin)
    inst.refresh_from_db()
    assert inst.is_paid is False
    assert inst.status == 'PENDING'


def test_double_reversal_is_rejected(loan, hq_admin, gl_accounts, api_client):
    payment, _ = record_payment(
        loan=loan, amount=Decimal('100.00'), user=hq_admin,
        payment_method='CASH',
    )
    r1 = _reverse(api_client, payment.id, hq_admin)
    assert r1.status_code == 200

    r2 = _reverse(api_client, payment.id, hq_admin, reason='Again')
    assert r2.status_code == 400
    assert b'already reversed' in r2.content.lower()
