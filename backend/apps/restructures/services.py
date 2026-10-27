from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import LoanRestructure, RestructureEvent
from apps.loans.models import Loan, LoanInstallment


# ============================================================
# Loan Restructure Service
# ============================================================
class RestructureService:

    # ============================================================
    # Amount calculation
    # ============================================================
    @staticmethod
    def compute_installment_amount(balance, annual_rate, months, frequency):
        """
        Simple monthly-rate calculation.
        annual_rate is a percent (e.g. 24.00 for 24% per year).
        Returns Decimal amount per installment.
        """
        if months <= 0:
            return Decimal('0.00')

        monthly_rate = Decimal(annual_rate) / Decimal('100') / Decimal('12')

        if monthly_rate == 0:
            # Zero-interest: straight-line
            per_period = Decimal(balance) / Decimal(months)
        else:
            # Standard amortization formula:
            # PMT = P * r / (1 - (1 + r)^-n)
            factor = monthly_rate / (
                Decimal('1') - (Decimal('1') + monthly_rate) ** (-months)
            )
            per_period = Decimal(balance) * factor

        # Adjust for non-monthly frequencies
        divisor = {'DAILY': 30, 'WEEKLY': 4, 'BIWEEKLY': 2, 'MONTHLY': 1}.get(
            frequency, 1,
        )
        per_period = per_period / Decimal(divisor)

        return per_period.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # ============================================================
    # Workflow
    # ============================================================
    @classmethod
    @transaction.atomic
    def propose(cls, loan, data, user):
        """
        Create a PROPOSED restructure. Computes new schedule and
        snapshot of original loan terms.
        """
        if loan.status not in ('ACTIVE', 'DISBURSED'):
            raise ValueError(
                f"Cannot restructure a loan in {loan.status} status."
            )

        # Only one open restructure per loan
        existing = LoanRestructure.objects.filter(
            loan=loan, status__in=['PROPOSED', 'APPROVED'],
        ).exists()
        if existing:
            raise ValueError(
                "This loan already has a pending restructure. "
                "Cancel or complete it first."
            )

        # Snapshot the current state
        original_balance = loan.balance_due
        original_installments = loan.installments.count()

        # Compute new terms
        new_start = data['new_start_date']
        new_maturity = data['new_maturity_date']
        new_count = int(data['new_installment_count'])
        new_rate = Decimal(data['new_interest_rate'])
        new_frequency = data['new_repayment_frequency']

        # Balance to be repaid (after any waivers)
        balance_to_schedule = original_balance
        penalties_waived = Decimal('0')

        if data.get('waive_penalties'):
            # Sum accrued penalties
            penalties_waived = (
                loan.installments
                .filter(is_paid=False)
                .aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('penalty_amount'))
                .get('total') or Decimal('0')
            )
            balance_to_schedule -= penalties_waived

        # Auto-compute installment amount if not provided
        months = int((new_maturity - new_start).days / 30) or 1
        installment_amount = cls.compute_installment_amount(
            balance_to_schedule, new_rate, months, new_frequency,
        )

        restructure = LoanRestructure.objects.create(
            loan=loan,
            branch=loan.branch,
            restructure_type=data['restructure_type'],
            reason=data['reason'],
            reason_notes=data.get('reason_notes', ''),

            original_principal=loan.amount,
            original_balance=original_balance,
            original_installment_count=original_installments,
            original_maturity_date=loan.maturity_date,

            new_start_date=new_start,
            new_maturity_date=new_maturity,
            new_installment_count=new_count,
            new_installment_amount=installment_amount,
            new_interest_rate=new_rate,
            new_repayment_frequency=new_frequency,

            waive_penalties=data.get('waive_penalties', False),
            penalties_waived_amount=penalties_waived,
            moratorium_days=int(data.get('moratorium_days', 0)),

            status='PROPOSED',
            proposed_by=user,
            proposed_at=timezone.now(),
        )

        RestructureEvent.objects.create(
            restructure=restructure,
            action='PROPOSED',
            user=user,
            comments=data.get('reason_notes', ''),
        )
        return restructure

    @classmethod
    @transaction.atomic
    def approve(cls, restructure, user, comments=''):
        if restructure.status != 'PROPOSED':
            raise ValueError(
                f"Cannot approve: restructure is {restructure.status}."
            )
        restructure.status = 'APPROVED'
        restructure.approved_by = user
        restructure.approved_at = timezone.now()
        restructure.save(update_fields=[
            'status', 'approved_by', 'approved_at', 'updated_at',
        ])
        RestructureEvent.objects.create(
            restructure=restructure, action='APPROVED',
            user=user, comments=comments,
        )
        return restructure

    @classmethod
    @transaction.atomic
    def reject(cls, restructure, user, reason=''):
        if restructure.status != 'PROPOSED':
            raise ValueError(
                f"Cannot reject: restructure is {restructure.status}."
            )
        restructure.status = 'REJECTED'
        restructure.rejected_by = user
        restructure.rejected_at = timezone.now()
        restructure.rejection_reason = reason
        restructure.save(update_fields=[
            'status', 'rejected_by', 'rejected_at',
            'rejection_reason', 'updated_at',
        ])
        RestructureEvent.objects.create(
            restructure=restructure, action='REJECTED',
            user=user, comments=reason,
        )
        return restructure

    # ============================================================
    # Apply — the big one
    # ============================================================
    @classmethod
    @transaction.atomic
    def apply(cls, restructure, user, comments=''):
        """
        Regenerate the loan's installment schedule per the approved terms.
        Historical paid installments are preserved. Unpaid future installments
        are replaced.
        """
        if restructure.status != 'APPROVED':
            raise ValueError(
                f"Cannot apply: restructure is {restructure.status}. "
                "Approve it first."
            )

        loan = restructure.loan
        today = timezone.now().date()

        # 1. Mark existing unpaid installments as superseded
        unpaid = loan.installments.filter(is_paid=False)
        superseded_count = unpaid.count()
        unpaid.update(
            status='SUPERSEDED',
        ) if hasattr(LoanInstallment, 'SUPERSEDED') else unpaid.delete()

        # 2. Recompute next installment number
        last_no = (
            loan.installments
            .aggregate(m=__import__('django.db.models', fromlist=['Max']).Max('installment_no'))
            .get('m') or 0
        )

        # 3. Update the loan's terms
        loan.interest_rate = restructure.new_interest_rate
        loan.repayment_frequency = restructure.new_repayment_frequency
        loan.start_date = restructure.new_start_date
        loan.maturity_date = restructure.new_maturity_date

        # 4. Recompute the balance
        # balance_due already excludes paid installments, so it's the base
        new_balance = loan.balance_due - restructure.penalties_waived_amount
        if new_balance < 0:
            new_balance = Decimal('0')
        loan.balance_due = new_balance

        # 5. Recalculate totals for the new schedule
        new_total_interest = (
            restructure.new_installment_amount * restructure.new_installment_count
        ) - new_balance
        if new_total_interest < 0:
            new_total_interest = Decimal('0')

        loan.total_interest = new_total_interest
        loan.total_penalties = max(
            Decimal('0'), loan.total_penalties - restructure.penalties_waived_amount,
        )
        loan.total_amount_due = new_balance + new_total_interest
        loan.save()

        # 6. Generate new installments
        interval_days = {
            'DAILY': 1, 'WEEKLY': 7, 'BIWEEKLY': 14, 'MONTHLY': 30,
        }.get(restructure.new_repayment_frequency, 30)

        schedule_start = restructure.new_start_date + timedelta(
            days=restructure.moratorium_days,
        )

        principal_per = (
            new_balance / restructure.new_installment_count
        ).quantize(Decimal('0.01'))
        interest_per = (
            new_total_interest / restructure.new_installment_count
        ).quantize(Decimal('0.01'))

        for i in range(1, restructure.new_installment_count + 1):
            due = schedule_start + timedelta(days=interval_days * i)
            principal_amt = principal_per
            # Adjust last installment for rounding
            if i == restructure.new_installment_count:
                accumulated_principal = principal_per * (i - 1)
                principal_amt = new_balance - accumulated_principal

            interest_amt = interest_per
            if i == restructure.new_installment_count:
                accumulated_interest = interest_per * (i - 1)
                interest_amt = new_total_interest - accumulated_interest

            LoanInstallment.objects.create(
                loan=loan,
                installment_no=last_no + i,
                due_date=due,
                principal_amount=principal_amt,
                interest_amount=interest_amt,
                penalty_amount=Decimal('0'),
                total_due=principal_amt + interest_amt,
                paid_amount=Decimal('0'),
                is_paid=False,
                status='PENDING',
            )

        # 7. GL entry for penalty waiver (if applicable)
        je = None
        if restructure.waive_penalties and restructure.penalties_waived_amount > 0:
            je = cls._post_penalty_waiver(restructure, user)
            restructure.journal_entry = je

        # 8. Mark restructure applied
        restructure.status = 'APPLIED'
        restructure.applied_at = timezone.now()
        restructure.save(update_fields=[
            'status', 'applied_at', 'journal_entry', 'updated_at',
        ])

        RestructureEvent.objects.create(
            restructure=restructure, action='APPLIED',
            user=user, comments=comments,
        )
        return restructure

    @classmethod
    @transaction.atomic
    def cancel(cls, restructure, user, comments=''):
        if restructure.status not in ('PROPOSED', 'APPROVED'):
            raise ValueError(
                f"Cannot cancel: restructure is {restructure.status}."
            )
        restructure.status = 'CANCELLED'
        restructure.save(update_fields=['status', 'updated_at'])
        RestructureEvent.objects.create(
            restructure=restructure, action='CANCELLED',
            user=user, comments=comments,
        )
        return restructure

    # ============================================================
    # GL for penalty waivers
    # ============================================================
    @staticmethod
    def _post_penalty_waiver(restructure, user):
        """
        DR Penalty Income (reversal)
        CR Loans Receivable - Penalties (write off)
        """
        from apps.accounting.services import AccountingService

        amount = restructure.penalties_waived_amount
        lines = [
            {'account_code': '4100', 'debit': amount,
             'memo': f'Waived penalties - {restructure.loan.loan_number}'},
            {'account_code': '1120', 'credit': amount,
             'memo': f'Waived penalties - {restructure.loan.loan_number}'},
        ]
        return AccountingService.create_journal_entry(
            organization=restructure.organization,
            entry_date=timezone.now().date(),
            reference=f'RESTR-{restructure.loan.loan_number}',
            description=f'Penalty waiver on restructure of {restructure.loan.loan_number}',
            lines=lines,
            source_type='Restructure',
            source_id=restructure.id,
            branch=restructure.branch,
            user=user,
        )