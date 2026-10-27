"""Tests for payment GL posting and reversal."""
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
