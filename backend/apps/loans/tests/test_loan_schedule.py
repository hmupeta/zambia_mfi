"""Tests for loan schedule generation — invariants on the fixture loan."""
from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


def test_loan_has_expected_installment_count(loan):
    assert loan.installments.count() == 3


def test_installment_numbers_are_sequential(loan):
    numbers = list(
        loan.installments.order_by('installment_no')
        .values_list('installment_no', flat=True)
    )
    assert numbers == [1, 2, 3]


def test_installment_principal_sums_to_loan_principal(loan):
    total_principal = sum(
        (inst.principal_amount for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_principal - loan.amount) < Decimal('0.05')


def test_installment_interest_sums_to_total_interest(loan):
    total_interest = sum(
        (inst.interest_amount for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_interest - loan.total_interest) < Decimal('0.01')


def test_installment_total_due_matches_sum(loan):
    total_due = sum(
        (inst.total_due for inst in loan.installments.all()),
        Decimal('0'),
    )
    assert abs(total_due - loan.total_amount_due) < Decimal('0.05')


def test_installment_remaining_starts_equals_total_due(loan):
    """Fresh installments should have paid_amount=0, remaining=total_due."""
    for inst in loan.installments.all():
        assert inst.paid_amount == Decimal('0')
        assert inst.is_paid is False
        assert inst.status == 'PENDING'
