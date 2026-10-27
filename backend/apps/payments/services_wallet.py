# apps/payments/services_wallet.py
"""
Branch wallet service — keeps BranchWallet balances in sync with real money
movement, logs every change to WalletTransaction, and provides the
reconciliation logic.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.db.models import Max

from .models import BranchWallet, WalletReconciliation, WalletTransaction


CHANNEL_MAP = {
    'CASH':         'cash',
    'BANK':         'bank',
    'MTN_MOMO':     'mobile_money',  # <--- Changed from 'momo'
    'AIRTEL_MONEY': 'mobile_money',  # <--- Changed from 'momo'
    'FAKE':         'mobile_money',  # <--- Changed from 'momo'
}


class WalletService:

    # ============================================================
    # Balance lookup / creation
    # ============================================================
    @staticmethod
    def get_or_create(branch):
        wallet, _ = BranchWallet.objects.get_or_create(branch=branch)
        return wallet

    # ============================================================
    # Movement tracking (updates balance + logs a transaction)
    # ============================================================
    @staticmethod
    @transaction.atomic
    def record_movement(branch, channel, amount, direction, reference='',
                        txn_type=None, user=None, notes=''):
        """
        Update BranchWallet balance AND write a WalletTransaction log row.

        channel:   CASH | BANK | MTN_MOMO | AIRTEL_MONEY
        direction: IN | OUT
        txn_type:  optional; inferred from direction if omitted
        """
        if not branch:
            return None

        channel_key = (channel or 'CASH').upper()
        field = CHANNEL_MAP.get(channel_key)
        if not field:
            return None

        # -- 1. Update the balance ---------------------------------
        wallet = (
            BranchWallet.objects
            .select_for_update()
            .filter(branch=branch)
            .first()
        )
        if not wallet:
            wallet = BranchWallet.objects.create(branch=branch)

        amount = Decimal(str(amount or 0))
        if amount <= 0:
            return wallet

        current = getattr(wallet, f'{field}_balance') or Decimal('0')
        if direction == 'IN':
            setattr(wallet, f'{field}_balance', current + amount)
        else:
            setattr(wallet, f'{field}_balance', current - amount)
        wallet.save(update_fields=[f'{field}_balance', 'updated_at'])

        # -- 2. Log to WalletTransaction ---------------------------
        if txn_type is None:
            txn_type = 'LOAN_COLLECTION' if direction == 'IN' else 'DISBURSEMENT'

        if direction == 'IN':
            WalletTransaction.objects.create(
                organization=branch.organization,
                branch=branch,
                transaction_type=txn_type,
                amount=amount,
                source_wallet=channel_key,
                dest_wallet='',
                reference=reference,
                notes=notes or f'IN via {channel_key}',
                created_by=user,
            )
        else:
            WalletTransaction.objects.create(
                organization=branch.organization,
                branch=branch,
                transaction_type=txn_type,
                amount=amount,
                source_wallet='',
                dest_wallet=channel_key,
                reference=reference,
                notes=notes or f'OUT via {channel_key}',
                created_by=user,
            )

        return wallet

    # ============================================================
    # Reconciliation
    # ============================================================
    @staticmethod
    def _next_recon_number(org):
        today = timezone.now().strftime('%Y%m%d')
        prefix = f'REC-{org.code.upper()}-{today}-'
        last = (
            WalletReconciliation.objects
            .filter(organization=org, reconciliation_number__startswith=prefix)
            .aggregate(m=Max('reconciliation_number'))['m']
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'{prefix}{seq:04d}'

    @staticmethod
    @transaction.atomic
    def reconcile(branch, physical_cash, physical_momo, physical_bank, notes, user):
        wallet = WalletService.get_or_create(branch)

        p_cash = Decimal(str(physical_cash or 0))
        p_momo = Decimal(str(physical_momo or 0))
        p_bank = Decimal(str(physical_bank or 0))

        s_cash = wallet.cash_balance or Decimal('0')
        s_momo = wallet.mobile_money_balance or Decimal('0')
        s_bank = wallet.bank_balance or Decimal('0')

        s_total = s_cash + s_momo + s_bank
        p_total = p_cash + p_momo + p_bank

        v_cash = p_cash - s_cash
        v_momo = p_momo - s_momo
        v_bank = p_bank - s_bank
        v_total = p_total - s_total

        is_balanced = (
            abs(v_cash) < Decimal('0.01')
            and abs(v_momo) < Decimal('0.01')
            and abs(v_bank) < Decimal('0.01')
        )

        recon = WalletReconciliation.objects.create(
            organization=branch.organization,
            branch=branch,
            reconciliation_number=WalletService._next_recon_number(branch.organization),
            system_cash=s_cash, system_momo=s_momo, system_bank=s_bank, system_total=s_total,
            physical_cash=p_cash, physical_momo=p_momo, physical_bank=p_bank, physical_total=p_total,
            variance_cash=v_cash, variance_momo=v_momo, variance_bank=v_bank, variance_total=v_total,
            status='BALANCED' if is_balanced else 'VARIANCE',
            notes=notes or '',
            reconciled_by=user,
        )

        wallet.last_reconciled_at = timezone.now()
        wallet.save(update_fields=['last_reconciled_at'])
        return recon

    @staticmethod
    @transaction.atomic
    def resolve(recon, user, notes):
        if recon.status != 'VARIANCE':
            raise ValueError('Only VARIANCE reconciliations can be resolved.')
        if not notes or not notes.strip():
            raise ValueError('Resolution notes are required.')
        recon.status = 'RESOLVED'
        recon.resolved_by = user
        recon.resolved_at = timezone.now()
        recon.resolution_notes = notes
        recon.save(update_fields=[
            'status', 'resolved_by', 'resolved_at', 'resolution_notes',
        ])
        return recon