from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from .models import GLAccount, JournalEntry, JournalLine


# Standard account codes used across the platform
class AccountCode:
    # Assets
    CASH_ON_HAND = '1010'
    BANK = '1020'
    MOBILE_MONEY = '1030'
    LOANS_RECEIVABLE_PRINCIPAL = '1100'
    LOANS_RECEIVABLE_INTEREST = '1110'
    LOANS_RECEIVABLE_PENALTY = '1120'
    INTEREST_RECEIVABLE = '1130'
    ALLOWANCE_LOAN_LOSSES = '1200'

    # Liabilities
    INTEREST_IN_SUSPENSE = '2100'
    LOAN_LOSS_PROVISION = '2300'

    # Equity
    RETAINED_EARNINGS = '3100'

    # Income
    INTEREST_INCOME = '4000'
    PENALTY_INCOME = '4100'
    FEE_INCOME = '4200'
    RECOVERY_INCOME = '4300'

    # Expenses
    LOAN_LOSS_EXPENSE = '5000'
    INTEREST_EXPENSE = '5100'
    OPERATING_EXPENSE = '5200'


class AccountingService:
    """Service class for creating journal entries and posting financial events."""

    @staticmethod
    def _get_account(org, code):
        return GLAccount.objects.get(organization=org, code=code, is_active=True)

    @staticmethod
    def _resolve_channel_account(channel):
        """Maps a payment/disbursement channel to a GL account code."""
        return {
            'CASH': AccountCode.CASH_ON_HAND,
            'BANK': AccountCode.BANK,
            'MTN_MOMO': AccountCode.MOBILE_MONEY,
            'AIRTEL_MONEY': AccountCode.MOBILE_MONEY,
        }.get(channel, AccountCode.CASH_ON_HAND)

    # ============================================================
    # Core journal creation
    # ============================================================
    @staticmethod
    @transaction.atomic
    def create_journal_entry(
        organization,
        entry_date,
        reference,
        description,
        lines,
        source_type=None,
        source_id=None,
        branch=None,
        user=None,
        post=True,
    ):
        """
        Creates a balanced journal entry.

        `lines` is a list of dicts:
            [{'account_code': '1100', 'debit': Decimal('1000'), 'credit': 0, 'memo': ''}]

        Raises ValueError if debits != credits.
        """
        total_debit = sum((Decimal(str(line.get('debit', 0))) for line in lines), Decimal('0'))
        total_credit = sum((Decimal(str(line.get('credit', 0))) for line in lines), Decimal('0'))

        if total_debit != total_credit:
            raise ValueError(
                f"Unbalanced journal entry: debits={total_debit}, credits={total_credit}"
            )
        if total_debit == 0:
            raise ValueError("Journal entry cannot be empty (zero-value).")

        je = JournalEntry.objects.create(
            organization=organization,
            branch=branch,
            entry_date=entry_date,
            reference=reference,
            description=description,
            source_type=source_type or 'Manual',
            source_id=source_id,
            created_by=user,
            is_posted=post,
        )

        for line in lines:
            account = AccountingService._get_account(organization, line['account_code'])
            JournalLine.objects.create(
                journal_entry=je,
                account=account,
                debit=Decimal(str(line.get('debit', 0))),
                credit=Decimal(str(line.get('credit', 0))),
                memo=line.get('memo', ''),
            )

        return je

    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(original_je, user=None, reason='Reversal'):
        """Creates a mirror-image journal entry that reverses the original."""
        if original_je.is_reversed:
            raise ValueError("Journal entry already reversed.")

        lines = []
        for line in original_je.lines.all():
            lines.append({
                'account_code': line.account.code,
                'debit': line.credit,   # swap
                'credit': line.debit,
                'memo': f"Reversal of {original_je.reference} - {reason}",
            })

        reversal = AccountingService.create_journal_entry(
            organization=original_je.organization,
            entry_date=timezone.now().date(),
            reference=f"REV-{original_je.reference}",
            description=f"Reversal: {original_je.description}",
            lines=lines,
            source_type=original_je.source_type,
            source_id=original_je.source_id,
            branch=original_je.branch,
            user=user,
        )

        original_je.is_reversed = True
        original_je.reversed_by = reversal
        original_je.save()

        return reversal

    # ============================================================
    # Domain-specific postings
    # ============================================================
    @staticmethod
    def post_loan_disbursement(loan, user=None):
        """
        DR Loans Receivable (Principal)
        CR Cash/Bank/Mobile Money
        """
        org = loan.organization
        credit_account = AccountingService._resolve_channel_account(loan.disbursement_channel)

        lines = [
            {
                'account_code': AccountCode.LOANS_RECEIVABLE_PRINCIPAL,
                'debit': loan.disbursed_amount,
                'memo': f'Principal disbursed for {loan.loan_number}',
            },
            {
                'account_code': credit_account,
                'credit': loan.disbursed_amount,
                'memo': f'Disbursement via {loan.disbursement_channel}',
            },
        ]
        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=loan.start_date,
            reference=loan.loan_number,
            description=f"Loan disbursement - {loan.loan_number}",
            lines=lines,
            source_type='Loan',
            source_id=loan.id,
            branch=loan.branch,
            user=user,
        )

    @staticmethod
    def post_loan_repayment(payment, allocations_summary=None):
        """
        DR Cash/Bank/Mobile Money
        CR Loans Receivable (Principal)
        CR Interest Income (on cash basis) OR Loans Receivable-Interest (if accrual)
        CR Penalty Income
        """
        org = payment.organization
        debit_account = AccountingService._resolve_channel_account(payment.payment_method)

        # Sum allocation portions from the payment's allocations
        principal = Decimal('0')
        interest = Decimal('0')
        penalty = Decimal('0')

        for alloc in payment.allocations.all():
            principal += alloc.principal_portion
            interest += alloc.interest_portion
            penalty += alloc.penalty_portion

        lines = [{
            'account_code': debit_account,
            'debit': payment.amount,
            'memo': f'Repayment for {payment.loan.loan_number}',
        }]
        if principal > 0:
            lines.append({
                'account_code': AccountCode.LOANS_RECEIVABLE_PRINCIPAL,
                'credit': principal,
                'memo': 'Principal portion',
            })
        if interest > 0:
            lines.append({
                'account_code': AccountCode.INTEREST_INCOME,
                'credit': interest,
                'memo': 'Interest income',
            })
        if penalty > 0:
            lines.append({
                'account_code': AccountCode.PENALTY_INCOME,
                'credit': penalty,
                'memo': 'Penalty income',
            })

        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=payment.received_at.date(),
            reference=payment.payment_number,
            description=f"Loan repayment - {payment.loan.loan_number}",
            lines=lines,
            source_type='Payment',
            source_id=payment.id,
            branch=payment.branch,
            user=payment.received_by,
        )

    @staticmethod
    def post_interest_accrual(loan, accrual_date, interest_amount, reference=None):
        """
        DR Interest Receivable (Asset)
        CR Interest Income
        """
        org = loan.organization
        if interest_amount <= 0:
            return None

        lines = [
            {
                'account_code': AccountCode.INTEREST_RECEIVABLE,
                'debit': interest_amount,
                'memo': f'Interest accrued for {loan.loan_number}',
            },
            {
                'account_code': AccountCode.INTEREST_INCOME,
                'credit': interest_amount,
                'memo': f'Interest income for {loan.loan_number}',
            },
        ]
        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=accrual_date,
            reference=reference or f"ACCR-{loan.loan_number}-{accrual_date}",
            description=f"Interest accrual - {loan.loan_number}",
            lines=lines,
            source_type='InterestAccrual',
            source_id=loan.id,
            branch=loan.branch,
        )

    @staticmethod
    def post_penalty_accrual(loan, accrual_date, penalty_amount, reference=None):
        """
        DR Penalties Receivable
        CR Penalty Income
        """
        org = loan.organization
        if penalty_amount <= 0:
            return None

        lines = [
            {
                'account_code': AccountCode.LOANS_RECEIVABLE_PENALTY,
                'debit': penalty_amount,
            },
            {
                'account_code': AccountCode.PENALTY_INCOME,
                'credit': penalty_amount,
            },
        ]
        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=accrual_date,
            reference=reference or f"PEN-{loan.loan_number}-{accrual_date}",
            description=f"Penalty accrual - {loan.loan_number}",
            lines=lines,
            source_type='PenaltyAccrual',
            source_id=loan.id,
            branch=loan.branch,
        )

    @staticmethod
    def post_provision(provision):
        """
        Posts a loan loss provision movement.
        DR Loan Loss Expense
        CR Loan Loss Provision (liability)
        """
        org = provision.loan.organization
        amount = provision.provision_movement

        if amount == 0:
            return None

        # If the movement is positive (increase provision), normal posting.
        # If negative (release), reverse the DR/CR.
        if amount > 0:
            lines = [
                {'account_code': AccountCode.LOAN_LOSS_EXPENSE, 'debit': amount},
                {'account_code': AccountCode.LOAN_LOSS_PROVISION, 'credit': amount},
            ]
        else:
            release = abs(amount)
            lines = [
                {'account_code': AccountCode.LOAN_LOSS_PROVISION, 'debit': release},
                {'account_code': AccountCode.LOAN_LOSS_EXPENSE, 'credit': release},
            ]

        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=provision.provision_date,
            reference=f"PROV-{provision.loan.loan_number}-{provision.provision_date}",
            description=f"Loan loss provision movement - {provision.loan.loan_number}",
            lines=lines,
            source_type='Provision',
            source_id=provision.id,
            branch=provision.loan.branch,
        )

    @staticmethod
    def post_write_off(loan, write_off_amount, write_off_date, user=None, reference=None):
        """
        DR Loan Loss Provision (uses accumulated provision)
        CR Loans Receivable - Principal

        If provision < outstanding, the shortfall hits Loan Loss Expense.
        """
        org = loan.organization
        lines = [
            {
                'account_code': AccountCode.LOAN_LOSS_PROVISION,
                'debit': write_off_amount,
            },
            {
                'account_code': AccountCode.LOANS_RECEIVABLE_PRINCIPAL,
                'credit': write_off_amount,
            },
        ]
        return AccountingService.create_journal_entry(
            organization=org,
            entry_date=write_off_date,
            reference=reference or f"WO-{loan.loan_number}",
            description=f"Loan write-off - {loan.loan_number}",
            lines=lines,
            source_type='WriteOff',
            source_id=loan.id,
            branch=loan.branch,
            user=user,
        )

    # ============================================================
    # Read helpers — Trial Balance, Income Statement, Balance Sheet
    # ============================================================
    @staticmethod
    def trial_balance(organization, as_of_date):
        """Returns a trial balance as of a date."""
        from django.db.models import Sum
        from .models import JournalLine

        lines = (
            JournalLine.objects
            .filter(
                journal_entry__organization=organization,
                journal_entry__entry_date__lte=as_of_date,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
            )
            .values('account__code', 'account__name', 'account__account_type')
            .annotate(total_debit=Sum('debit'), total_credit=Sum('credit'))
            .order_by('account__code')
        )
        return list(lines)

    @staticmethod
    def account_balance(organization, account_code, as_of_date):
        """Returns net balance for a single account, signed per its normal side."""
        from django.db.models import Sum
        from .models import JournalLine

        result = (
            JournalLine.objects
            .filter(
                journal_entry__organization=organization,
                journal_entry__entry_date__lte=as_of_date,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
                account__code=account_code,
            )
            .aggregate(dr=Sum('debit'), cr=Sum('credit'))
        )
        dr = result['dr'] or Decimal('0')
        cr = result['cr'] or Decimal('0')

        account = GLAccount.objects.get(organization=organization, code=account_code)
        if account.is_debit_normal:
            return dr - cr
        return cr - dr

    @staticmethod
    def income_statement(organization, from_date, to_date):
        """Returns Revenue, Expenses, and Net Income for a period."""
        from django.db.models import Sum
        from .models import JournalLine

        rows = (
            JournalLine.objects
            .filter(
                journal_entry__organization=organization,
                journal_entry__entry_date__gte=from_date,
                journal_entry__entry_date__lte=to_date,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
                account__account_type__in=['INCOME', 'EXPENSE'],
            )
            .values('account__code', 'account__name', 'account__account_type')
            .annotate(dr=Sum('debit'), cr=Sum('credit'))
            .order_by('account__code')
        )

        revenue = Decimal('0')
        expenses = Decimal('0')
        detail = []

        for row in rows:
            dr = row['dr'] or Decimal('0')
            cr = row['cr'] or Decimal('0')
            if row['account__account_type'] == 'INCOME':
                net = cr - dr
                revenue += net
            else:
                net = dr - cr
                expenses += net

            detail.append({
                'code': row['account__code'],
                'name': row['account__name'],
                'type': row['account__account_type'],
                'amount': float(net),
            })

        return {
            'from_date': str(from_date),
            'to_date': str(to_date),
            'revenue': float(revenue),
            'expenses': float(expenses),
            'net_income': float(revenue - expenses),
            'accounts': detail,
        }

    @staticmethod
    def balance_sheet(organization, as_of_date):
        """Returns Assets, Liabilities, Equity as of a date."""
        from django.db.models import Sum
        from .models import JournalLine

        rows = (
            JournalLine.objects
            .filter(
                journal_entry__organization=organization,
                journal_entry__entry_date__lte=as_of_date,
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
                account__account_type__in=['ASSET', 'LIABILITY', 'EQUITY'],
            )
            .values('account__code', 'account__name', 'account__account_type',
                    'account__is_contra')
            .annotate(dr=Sum('debit'), cr=Sum('credit'))
            .order_by('account__code')
        )

        assets, liabilities, equity = [], [], []
        totals = {'ASSET': Decimal('0'), 'LIABILITY': Decimal('0'), 'EQUITY': Decimal('0')}

        for row in rows:
            dr = row['dr'] or Decimal('0')
            cr = row['cr'] or Decimal('0')
            atype = row['account__account_type']

            if atype == 'ASSET':
                net = dr - cr
            elif atype in ('LIABILITY', 'EQUITY'):
                net = cr - dr
            else:
                net = Decimal('0')

            entry = {
                'code': row['account__code'],
                'name': row['account__name'],
                'amount': float(net),
                'is_contra': row['account__is_contra'],
            }
            if atype == 'ASSET':
                assets.append(entry)
            elif atype == 'LIABILITY':
                liabilities.append(entry)
            else:
                equity.append(entry)

            totals[atype] += net

        return {
            'as_of_date': str(as_of_date),
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'total_assets': float(totals['ASSET']),
            'total_liabilities': float(totals['LIABILITY']),
            'total_equity': float(totals['EQUITY']),
            'balanced': totals['ASSET'] == (totals['LIABILITY'] + totals['EQUITY']),
        }