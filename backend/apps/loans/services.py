from datetime import date, timedelta
from decimal import Decimal
from .models import Loan, LoanInstallment

class LoanService:
    @staticmethod
    def generate_installments(loan):
        """Generate installment schedule for a loan."""
        installments = []
        amount = loan.amount
        interest_rate = loan.interest_rate
        tenure_months = (loan.maturity_date - loan.start_date).days // 30
        
        if loan.interest_method == 'FLAT':
            # Flat interest
            total_interest = amount * (interest_rate / 100) * tenure_months
            total_due = amount + total_interest
            principal_per_installment = amount / tenure_months
            interest_per_installment = total_interest / tenure_months
        elif loan.interest_method == 'REDUCING_BALANCE':
            # Reducing balance (annuity)
            monthly_rate = interest_rate / 100
            total_installments = tenure_months
            factor = monthly_rate / (1 - (1 + monthly_rate) ** -total_installments)
            installment_amount = amount * factor
            total_interest = (installment_amount * total_installments) - amount
            total_due = amount + total_interest
            principal_per_installment = installment_amount
            interest_per_installment = installment_amount
        else:
            # Daily interest
            total_interest = amount * (interest_rate / 100) * (loan.maturity_date - loan.start_date).days
            total_due = amount + total_interest
            principal_per_installment = amount / tenure_months
            interest_per_installment = total_interest / tenure_months
        
        # Update loan totals
        loan.total_interest = total_interest
        loan.total_amount_due = total_due
        loan.balance_due = total_due
        loan.save()
        
        # Generate installments
        if loan.repayment_frequency == 'WEEKLY':
            # Weekly payments
            num_installments = tenure_months * 4
            interval = 7
        elif loan.repayment_frequency == 'BIWEEKLY':
            num_installments = tenure_months * 2
            interval = 14
        elif loan.repayment_frequency == 'MONTHLY':
            num_installments = tenure_months
            interval = 30
        else:  # DAILY
            num_installments = (loan.maturity_date - loan.start_date).days
            interval = 1
        
        for i in range(1, num_installments + 1):
            due_date = loan.start_date + timedelta(days=i * interval)
            installments.append({
                'loan': loan,
                'installment_no': i,
                'due_date': due_date,
                'principal_amount': principal_per_installment,
                'interest_amount': interest_per_installment,
                'total_due': principal_per_installment + interest_per_installment,
            })
        
        # Bulk create installments
        LoanInstallment.objects.bulk_create(
            [LoanInstallment(**data) for data in installments]
        )
        
        return installments
    
    @staticmethod
    def calculate_interest(loan):
        """Calculate total interest for a loan."""
        amount = loan.amount
        rate = loan.interest_rate
        
        if loan.interest_method == 'FLAT':
            return amount * (rate / 100) * (loan.maturity_date - loan.start_date).days / 30
        elif loan.interest_method == 'REDUCING_BALANCE':
            return amount * (rate / 100)  # Simplified - proper annuity formula in production
        else:
            return amount * (rate / 100) * (loan.maturity_date - loan.start_date).days