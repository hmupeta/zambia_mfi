from datetime import date
from decimal import Decimal
from django.db import transaction

from .models import LoanLossProvision, GLAccount
from .services import AccountingService, AccountCode


class ProvisioningService:
    """
    BoZ Microfinance Classification and Provisioning Directives (2018).

    Buckets:
        0 days         → Performing   → 1% general provision
        1–30 days      → Watch        → 5%
        31–90 days     → Substandard  → 25%
        91–180 days    → Doubtful     → 75%
        181+ days      → Loss         → 100%
    """

    BUCKETS = [
        (0, 0, 'PERFORMING', Decimal('0.01')),
        (1, 30, 'WATCH', Decimal('0.05')),
        (31, 90, 'SUBSTANDARD', Decimal('0.25')),
        (91, 180, 'DOUBTFUL', Decimal('0.75')),
        (181, 999999, 'LOSS', Decimal('1.00')),
    ]

    @classmethod
    def classify(cls, days_past_due: int):
        for min_dpd, max_dpd, label, rate in cls.BUCKETS:
            if min_dpd <= days_past_due <= max_dpd:
                return label, rate
        return 'LOSS', Decimal('1.00')

    @classmethod
    def compute_days_past_due(cls, loan, as_of_date: date) -> int:
        """DPD = days since the oldest unpaid installment was due."""
        oldest = (
            loan.installments
            .filter(is_paid=False, due_date__lt=as_of_date)
            .order_by('due_date')
            .first()
        )
        if not oldest:
            return 0
        return (as_of_date - oldest.due_date).days

    @classmethod
    @transaction.atomic
    def run_for_organization(cls, organization, as_of_date: date = None):
        """
        Classify all active loans, compute provisions, post the movement to the GL.
        Returns a summary dict.
        """
        from apps.loans.models import Loan

        if as_of_date is None:
            as_of_date = date.today()

        # Only loans that are actually disbursed and not closed
        active_loans = Loan.objects.filter(
            organization=organization,
            status__in=['ACTIVE', 'DISBURSED'],
        ).select_related('branch', 'client')

        summary = {
            'as_of_date': str(as_of_date),
            'loans_processed': 0,
            'total_provision': Decimal('0'),
            'total_movement': Decimal('0'),
            'by_classification': {},
        }

        for loan in active_loans:
            dpd = cls.compute_days_past_due(loan, as_of_date)
            classification, rate = cls.classify(dpd)

            outstanding = loan.balance_due or Decimal('0')
            new_provision = (outstanding * rate).quantize(Decimal('0.01'))

            # Find the most recent provision for this loan (prior period)
            prior = (
                loan.provisions
                .filter(provision_date__lt=as_of_date)
                .order_by('-provision_date')
                .first()
            )
            prior_amount = prior.provision_amount if prior else Decimal('0')
            movement = new_provision - prior_amount

            provision, created = LoanLossProvision.objects.update_or_create(
                loan=loan,
                provision_date=as_of_date,
                defaults={
                    'classification': classification,
                    'days_past_due': dpd,
                    'outstanding_balance': outstanding,
                    'provision_rate': rate,
                    'provision_amount': new_provision,
                    'prior_provision': prior_amount,
                    'provision_movement': movement,
                },
            )

            # Post the movement to the GL
            if movement != 0:
                je = AccountingService.post_provision(provision)
                if je:
                    provision.journal_entry = je
                    provision.save(update_fields=['journal_entry'])

            summary['loans_processed'] += 1
            summary['total_provision'] += new_provision
            summary['total_movement'] += movement
            summary['by_classification'].setdefault(classification, 0)
            summary['by_classification'][classification] += 1

        return summary