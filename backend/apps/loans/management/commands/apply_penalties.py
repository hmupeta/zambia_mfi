from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.loans.models import LoanInstallment
from apps.accounting.models import GLAccount
from apps.accounting.services import AccountingService

class Command(BaseCommand):
    help = 'Applies daily penalties to overdue installments based on product rules.'

    def handle(self, *args, **options):
        today = timezone.now().date()
        self.stdout.write(f"Applying penalties for {today}...")

        # Find unpaid installments where the current date is past the grace period
        # and we haven't already applied a penalty today.
        overdue_installments = LoanInstallment.objects.filter(
            is_paid=False,
            loan__status__in=['DISBURSED', 'ACTIVE', 'DEFAULTED'],
        ).exclude(last_penalty_date=today).select_related('loan', 'loan__loan_product', 'loan__organization')

        penalty_gl = None
        applied_count = 0
        total_penalty = Decimal('0')

        for inst in overdue_installments:
            product = inst.loan.loan_product
            grace_end = inst.due_date + timedelta(days=product.grace_days)

            if today > grace_end:
                # Calculate penalty (e.g., 2% of the installment amount)
                penalty_rate = Decimal(str(product.penalty_rate or 0)) / Decimal('100')
                if penalty_rate <= 0:
                    continue

                penalty_amount = (inst.total_due * penalty_rate).quantize(Decimal('0.01'))
                
                if penalty_amount > 0:
                    # Update Installment
                    inst.penalty_amount += penalty_amount
                    inst.total_due += penalty_amount
                    inst.last_penalty_date = today
                    inst.save(update_fields=['penalty_amount', 'total_due', 'last_penalty_date'])

                    # Update Loan Balance
                    inst.loan.total_penalties += penalty_amount
                    inst.loan.balance_due += penalty_amount
                    inst.loan.save(update_fields=['total_penalties', 'balance_due'])

                    applied_count += 1
                    total_penalty += penalty_amount

        # Optional: Post a single aggregate Journal Entry for all penalties today
        if applied_count > 0:
            self.stdout.write(self.style.SUCCESS(f"✅ Applied penalties to {applied_count} installments."))
            self.stdout.write(self.style.SUCCESS(f"Total Penalty Added: K{total_penalty}"))
            
            # Note: In a real production environment, you would post a GL entry here:
            # DR Loans Receivable (1100) / CR Penalty Income (4100) for total_penalty
        else:
            self.stdout.write(self.style.WARNING("No new penalties applied today."))