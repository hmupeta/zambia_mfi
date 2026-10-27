from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.core.models import Organization
from apps.loans.models import Loan, LoanInstallment
from apps.accounting.services import AccountingService


class Command(BaseCommand):
    help = 'Accrue daily interest for all active loans in every organization.'

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Specific org code.')
        parser.add_argument('--as-of', help='YYYY-MM-DD (defaults to today).')

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options['org']:
            orgs = orgs.filter(code=options['org'])

        as_of = date.fromisoformat(options['as_of']) if options['as_of'] else date.today()

        for org in orgs:
            self.stdout.write(f"\nAccruing interest for {org.code}...")
            loans = Loan.objects.filter(organization=org, status__in=['ACTIVE', 'DISBURSED'])

            total_accrued = Decimal('0')
            count = 0

            for loan in loans:
                # Find installments not yet paid
                for inst in loan.installments.filter(is_paid=False):
                    # Simple daily accrual: interest_amount / days_in_tenure
                    days = (loan.maturity_date - loan.start_date).days or 1
                    daily_interest = (inst.interest_amount / days).quantize(Decimal('0.01'))
                    je = AccountingService.post_interest_accrual(
                        loan, as_of, daily_interest,
                        reference=f"ACCR-{loan.loan_number}-{as_of}-{inst.installment_no}",
                    )
                    if je:
                        total_accrued += daily_interest
                        count += 1

            self.stdout.write(self.style.SUCCESS(
                f'  Accrued {count} entries totalling {total_accrued}'
            ))

        self.stdout.write(self.style.SUCCESS('\n✅ Interest accrual complete.'))