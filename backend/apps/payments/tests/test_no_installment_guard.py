"""A payment against a loan with no installments must not crash the GL post."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.loans.models import Loan
from apps.payments.services_admin import record_payment


pytestmark = pytest.mark.django_db


def test_payment_with_no_installments_skips_gl(
    org, branch, client, loan_product, hq_admin, gl_accounts,
):
    loan = Loan.objects.create(
        organization=org, branch=branch, client=client, loan_product=loan_product,
        loan_number='LN-NOINST-0001',
        amount=Decimal('5000'), total_interest=Decimal('500'),
        total_amount_due=Decimal('5500'), disbursed_amount=Decimal('5000'),
        balance_due=Decimal('5500'),
        start_date=date.today(),
        maturity_date=date.today() + timedelta(days=180),
        interest_rate=Decimal('10'), interest_method='FLAT',
        repayment_frequency='MONTHLY', status='DISBURSED',
    )
    # Deliberately no installments created

    payment, total_allocated = record_payment(
        loan=loan, amount=Decimal('500'), user=hq_admin,
        payment_method='CASH',
    )

    # Should not raise, but should not have posted a JE either
    assert payment.journal_entry is None
    assert total_allocated == Decimal('0')
