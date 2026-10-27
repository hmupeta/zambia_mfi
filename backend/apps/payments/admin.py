# apps/payments/services_admin.py
"""
Payment allocation engine + GL posting.

Splits a payment amount across a loan's unpaid installments in the order:
    penalties -> interest -> principal

Then posts a balanced journal entry:
    DR  Cash/Bank/MoMo       (payment.amount)
    CR  Loans Receivable     (sum of principal portions)
    CR  Interest Income      (sum of interest portions)
    CR  Penalty Income       (sum of penalty portions)

Also updates the BranchWallet balance and logs a WalletTransaction row.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Payment, PaymentAllocation
from apps.accounting.models import GLAccount
from apps.accounting.services import AccountingService


# ============================================================
# Installment breakdown
# ============================================================
def _remaining_breakdown(installment):
    """
    Given an installment with `paid_amount`, compute the remaining
    penalty / interest / principal assuming the paid amount was applied
    penalty-first (standard convention).
    """
    penalty = Decimal(installment.penalty_amount or 0)
    interest = Decimal(installment.interest_amount or 0)
    principal = Decimal(installment.principal_amount or 0)
    paid = Decimal(installment.paid_amount or 0)

    remaining_penalty = max(Decimal('0'), penalty - min(paid, penalty))
    after_penalty = max(Decimal('0'), paid - penalty)

    remaining_interest = max(Decimal('0'), interest - min(after_penalty, interest))
    after_interest = max(Decimal('0'), after_penalty - interest)

    remaining_principal = max(Decimal('0'), principal - min(after_interest, principal))

    return {
        'penalty': remaining_penalty,
        'interest': remaining_interest,
        'principal': remaining_principal,
        'total': remaining_penalty + remaining_interest + remaining_principal,
    }


def preview_allocation(loan, amount):
    """Return a plan describing how `amount` would be split across installments."""
    amount = Decimal(str(amount))
    remaining = amount
    plan = []

    installments = loan.installments.filter(is_paid=False).order_by('installment_no')

    for inst in installments:
        if remaining <= 0:
            break

        breakdown = _remaining_breakdown(inst)
        if breakdown['total'] <= 0:
            continue

        alloc_penalty = min(remaining, breakdown['penalty'])
        remaining -= alloc_penalty

        alloc_interest = min(remaining, breakdown['interest'])
        remaining -= alloc_interest

        alloc_principal = min(remaining, breakdown['principal'])
        remaining -= alloc_principal

        if alloc_penalty or alloc_interest or alloc_principal:
            plan.append({
                'installment_id': inst.id,
                'installment_no': inst.installment_no,
                'due_date': str(inst.due_date),
                'penalty': float(alloc_penalty),
                'interest': float(alloc_interest),
                'principal': float(alloc_principal),
                'subtotal': float(alloc_penalty + alloc_interest + alloc_principal),
            })

    return {
        'plan': plan,
        'allocated': float(amount - remaining),
        'unallocated': float(remaining),
    }


# ============================================================
# GL posting
# ============================================================
def _resolve_gl(org, code, name_hint=None):
    """Find a GL account by exact code, then by name substring."""
    acc = GLAccount.objects.filter(
        organization=org, code=code, is_active=True,
    ).first()
    if acc:
        return acc
    if name_hint:
        return GLAccount.objects.filter(
            organization=org, name__icontains=name_hint, is_active=True,
        ).first()
    return None


def _post_payment_to_gl(payment):
    """
    Post a loan repayment to the GL.
    Idempotent — if a journal_entry already exists, do nothing.
    """
    if payment.journal_entry_id:
        return payment.journal_entry

    org = payment.organization

    principal = sum(
        (Decimal(a.principal_portion or 0) for a in payment.allocations.all()),
        Decimal('0'),
    )
    interest = sum(
        (Decimal(a.interest_portion or 0) for a in payment.allocations.all()),
        Decimal('0'),
    )
    penalty = sum(
        (Decimal(a.penalty_portion or 0) for a in payment.allocations.all()),
        Decimal('0'),
    )

    debit_code = {
        'CASH':         '1010',
        'BANK':         '1020',
        'MTN_MOMO':     '1030',
        'AIRTEL_MONEY': '1030',
    }.get(payment.payment_method, '1010')

    debit_gl = _resolve_gl(org, debit_code)
    if not debit_gl:
        raise ValueError(
            f"No GL account with code {debit_code} for payment method "
            f"{payment.payment_method}. Configure the chart of accounts."
        )

    principal_gl = (
        _resolve_gl(org, '1100', 'loans receivable')
        or _resolve_gl(org, '1100')
    )
    interest_gl = _resolve_gl(org, '4000', 'interest income')
    penalty_gl = _resolve_gl(org, '4100', 'penalty income')

    if principal > 0 and not principal_gl:
        raise ValueError("No Loans Receivable GL account found (expected code 1100).")
    if interest > 0 and not interest_gl:
        raise ValueError("No Interest Income GL account found (expected code 4000).")
    if penalty > 0 and not penalty_gl:
        raise ValueError("No Penalty Income GL account found (expected code 4100).")

    lines = [{
        'account_code': debit_gl.code,
        'debit': float(payment.amount),
        'credit': 0,
        'memo': f'Payment {payment.payment_number}',
    }]

    if principal > 0:
        lines.append({
            'account_code': principal_gl.code,
            'debit': 0,
            'credit': float(principal),
            'memo': 'Principal recovery',
        })
    if interest > 0:
        lines.append({
            'account_code': interest_gl.code,
            'debit': 0,
            'credit': float(interest),
            'memo': 'Interest income on repayment',
        })
    if penalty > 0:
        lines.append({
            'account_code': penalty_gl.code,
            'debit': 0,
            'credit': float(penalty),
            'memo': 'Penalty income',
        })

    entry_date = (
        payment.received_at.date() if payment.received_at
        else timezone.now().date()
    )

    je = AccountingService.create_journal_entry(
        organization=org,
        entry_date=entry_date,
        reference=payment.payment_number,
        description=(
            f'Loan repayment: '
            f'{payment.loan.loan_number if payment.loan else ""}'
        ),
        lines=lines,
        source_type='Payment',
        source_id=payment.id,
        branch=payment.branch,
        user=payment.received_by,
    )

    payment.journal_entry = je
    payment.save(update_fields=['journal_entry'])
    return je


# ============================================================
# Record payment
# ============================================================
@transaction.atomic
def record_payment(loan, amount, user, **kwargs):
    """
    Create a Payment, allocate it across installments, update each
    installment's paid_amount and is_paid, update loan balance_due,
    post the journal entry to the GL, and update the branch wallet.
    """
    amount = Decimal(str(amount))

    # -- Generate payment number -----------------------
    from django.db.models import Max
    last = Payment.objects.filter(
        organization=loan.organization,
    ).aggregate(m=Max('payment_number'))['m']
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    today = timezone.now().strftime('%Y%m%d')
    payment_number = f"PAY-{loan.organization.code.upper()}-{today}-{seq:05d}"

    # -- Create the payment record ---------------------
    payment = Payment.objects.create(
        organization=loan.organization,
        payment_number=payment_number,
        loan=loan,
        client=loan.client,
        branch=loan.branch,
        amount=amount,
        payment_method=kwargs.get('payment_method', 'CASH'),
        payment_type=kwargs.get('payment_type', 'INSTALLMENT'),
        transaction_ref=kwargs.get('transaction_ref', ''),
        notes=kwargs.get('notes', ''),
        received_by=user,
    )

    # -- Allocate across installments ------------------
    plan = preview_allocation(loan, amount)['plan']
    total_allocated = Decimal('0')

    for row in plan:
        inst = loan.installments.get(id=row['installment_id'])
        penalty = Decimal(str(row['penalty']))
        interest = Decimal(str(row['interest']))
        principal = Decimal(str(row['principal']))
        subtotal = penalty + interest + principal

        PaymentAllocation.objects.create(
            payment=payment,
            installment=inst,
            principal_portion=principal,
            interest_portion=interest,
            penalty_portion=penalty,
        )

        inst.paid_amount = Decimal(inst.paid_amount or 0) + subtotal
        if inst.paid_amount >= Decimal(inst.total_due or 0):
            inst.is_paid = True
            inst.paid_at = timezone.now()
            inst.status = 'PAID'
        inst.save(update_fields=['paid_amount', 'is_paid', 'paid_at', 'status'])
        total_allocated += subtotal

    # -- Update loan balance ---------------------------
    loan.balance_due = max(
        Decimal('0'),
        Decimal(loan.balance_due or 0) - total_allocated,
    )
    if loan.balance_due == 0:
        loan.is_fully_repaid = True
        loan.status = 'CLOSED'
        loan.closed_at = timezone.now()
    loan.save(update_fields=[
        'balance_due', 'is_fully_repaid', 'status', 'closed_at', 'updated_at',
    ])

    # -- Post to GL ------------------------------------
    _post_payment_to_gl(payment)

    # -- Update branch wallet balance ------------------
    try:
        from .services_wallet import WalletService
        WalletService.record_movement(
            branch=loan.branch,
            channel=payment.payment_method,
            amount=amount,
            direction='IN',
            reference=payment.payment_number,
            txn_type='LOAN_COLLECTION',
            user=user,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Wallet update failed for {payment.payment_number}: {e}"
        )

    return payment, total_allocated