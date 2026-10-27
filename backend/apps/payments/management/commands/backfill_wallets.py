# apps/payments/management/commands/backfill_wallets.py
"""
Backfill BranchWallet balances and WalletTransaction logs from existing
Payment and Loan records.

Usage:
    python manage.py backfill_wallets --reset
"""
from django.core.management.base import BaseCommand

from apps.payments.models import Payment, BranchWallet, WalletTransaction
from apps.payments.services_wallet import WalletService
from apps.loans.models import Loan


class Command(BaseCommand):
    help = 'Backfill branch wallet balances + transaction log from historical data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Reset all wallet balances and delete prior transaction log first',
        )

    def handle(self, *args, **options):
        if options['reset']:
            BranchWallet.objects.update(
                cash_balance=0, mobile_money_balance=0, bank_balance=0,
            )
            WalletTransaction.objects.all().delete()
            self.stdout.write(self.style.WARNING('Reset all wallet balances + txn log'))

        payments_done = 0
        for p in Payment.objects.filter(is_reversed=False).order_by('received_at'):
            WalletService.record_movement(
                branch=p.branch,
                channel=p.payment_method,
                amount=p.amount,
                direction='IN',
                reference=p.payment_number,
                txn_type='LOAN_COLLECTION',
                user=p.received_by,
            )
            payments_done += 1

        loans_done = 0
        for loan in Loan.objects.filter(
            status__in=['DISBURSED', 'ACTIVE', 'CLOSED'],
        ).order_by('start_date'):
            if not loan.disbursed_amount:
                continue
            WalletService.record_movement(
                branch=loan.branch,
                channel=loan.disbursement_channel or 'CASH',
                amount=loan.disbursed_amount,
                direction='OUT',
                reference=loan.loan_number,
                txn_type='DISBURSEMENT',
                user=loan.approved_by,
            )
            loans_done += 1

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled {payments_done} payments and {loans_done} loan disbursements.'
        ))