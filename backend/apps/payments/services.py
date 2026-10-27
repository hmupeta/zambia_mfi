from decimal import Decimal
from .models import Payment, PaymentAllocation, BranchWallet, WalletTransaction
from apps.loans.models import LoanInstallment

class PaymentService:
    @staticmethod
    def process_payment(payment_data, user):
        """Process a loan payment and allocate to installments."""
        loan = payment_data['loan']
        amount = payment_data['amount']
        
        # Get unpaid installments (oldest first)
        installments = loan.installments.filter(is_paid=False).order_by('due_date')
        
        if not installments.exists():
            raise ValueError("Loan is fully paid")
        
        remaining = amount
        allocations = []
        
        # Allocate payment to installments
        for installment in installments:
            if remaining <= 0:
                break
            
            installment_remaining = installment.total_due - installment.paid_amount
            allocation_amount = min(remaining, installment_remaining)
            
            # Calculate portions
            principal_portion = min(allocation_amount, installment.principal_amount - installment.paid_amount)
            remaining_after_principal = allocation_amount - principal_portion
            
            interest_portion = min(remaining_after_principal, installment.interest_amount)
            remaining_after_interest = remaining_after_principal - interest_portion
            
            penalty_portion = min(remaining_after_interest, installment.penalty_amount)
            
            # Update installment
            installment.paid_amount += allocation_amount
            if installment.paid_amount >= installment.total_due:
                installment.is_paid = True
                installment.paid_at = payment_data['received_at'] if 'received_at' in payment_data else None
                installment.status = 'PAID'
            elif installment.paid_amount > 0:
                installment.status = 'PARTIAL'
            
            installment.save()
            
            allocations.append({
                'installment': installment,
                'principal_portion': principal_portion,
                'interest_portion': interest_portion,
                'penalty_portion': penalty_portion
            })
            
            remaining -= allocation_amount
        
        # Create payment
        payment = Payment.objects.create(
            payment_number=f"PAY-{loan.loan_number}-{payment_data.get('sequence', 1)}",
            loan=loan,
            branch=loan.branch,
            received_by=user,
            client=loan.client,
            amount=amount,
            payment_method=payment_data.get('payment_method', 'CASH'),
            transaction_ref=payment_data.get('transaction_ref', ''),
            payment_type=payment_data.get('payment_type', 'INSTALLMENT'),
            notes=payment_data.get('notes', '')
        )
        
        # Create allocations
        for alloc in allocations:
            PaymentAllocation.objects.create(
                payment=payment,
                installment=alloc['installment'],
                principal_portion=alloc['principal_portion'],
                interest_portion=alloc['interest_portion'],
                penalty_portion=alloc['penalty_portion']
            )
        
        # Update loan balance
        loan.balance_due = loan.total_amount_due - (loan.total_amount_due - sum(
            alloc['installment'].total_due for alloc in allocations
        ))
        loan.save()
        
        # Update branch wallet
        PaymentService.update_wallet(payment, user)
        
        return payment, allocations
    
    @staticmethod
    def update_wallet(payment, user):
        """Update branch wallet based on payment."""
        wallet, _ = BranchWallet.objects.get_or_create(branch=payment.branch)
        
        if payment.payment_method == 'CASH':
            wallet.cash_balance += payment.amount
        elif payment.payment_method in ['MTN_MOMO', 'AIRTEL_MONEY']:
            wallet.mobile_money_balance += payment.amount
        elif payment.payment_method == 'BANK':
            wallet.bank_balance += payment.amount
        
        wallet.save()
        
        # Create wallet transaction
        WalletTransaction.objects.create(
            branch=payment.branch,
            transaction_type='LOAN_COLLECTION',
            amount=payment.amount,
            source_wallet=payment.payment_method,
            reference=payment.payment_number,
            created_by=user
        )