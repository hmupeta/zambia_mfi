"""Tests for wallet balance tracking and reconciliation."""
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
