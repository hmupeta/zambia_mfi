"""Tests for the payment allocation engine (penalty -> interest -> principal)."""
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
