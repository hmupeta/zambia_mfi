from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Expense, ExpenseApproval
from apps.accounting.services import AccountingService


class ExpenseService:
    """Handles expense workflow and GL posting."""

    # ============================================================
    # Number generation
    # ============================================================
    @staticmethod
    def generate_expense_number(organization):
        """EXP-<ORG>-<YYYYMMDD>-<seq>"""
        today = date.today()
        prefix = f"EXP-{organization.code.upper()}-{today.strftime('%Y%m%d')}"
        last = (
            Expense.objects
            .filter(organization=organization, expense_number__startswith=prefix)
            .aggregate(m=Max('expense_number'))
            .get('m')
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[-1]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}-{seq:04d}"

    # ============================================================
    # Workflow transitions
    # ============================================================
    @classmethod
    @transaction.atomic
    def submit(cls, expense, user, comments=''):
        if expense.status != 'DRAFT':
            raise ValueError(f"Cannot submit: expense is {expense.status}.")
        if expense.amount <= 0:
            raise ValueError("Expense amount must be greater than zero.")

        expense.status = 'SUBMITTED'
        expense.submitted_by = user
        expense.submitted_at = timezone.now()
        expense.save(update_fields=['status', 'submitted_by', 'submitted_at', 'updated_at'])

        ExpenseApproval.objects.create(
            expense=expense, action='SUBMITTED', user=user, comments=comments,
        )
        return expense

    @classmethod
    @transaction.atomic
    def approve(cls, expense, user, comments=''):
        if expense.status != 'SUBMITTED':
            raise ValueError(f"Cannot approve: expense is {expense.status}.")

        expense.status = 'APPROVED'
        expense.approved_by = user
        expense.approved_at = timezone.now()
        expense.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        ExpenseApproval.objects.create(
            expense=expense, action='APPROVED', user=user, comments=comments,
        )
        return expense

    @classmethod
    @transaction.atomic
    def reject(cls, expense, user, comments=''):
        if expense.status not in ('SUBMITTED', 'APPROVED'):
            raise ValueError(f"Cannot reject: expense is {expense.status}.")

        expense.status = 'REJECTED'
        expense.save(update_fields=['status', 'updated_at'])

        ExpenseApproval.objects.create(
            expense=expense, action='REJECTED', user=user, comments=comments,
        )
        return expense

    @classmethod
    @transaction.atomic
    def mark_paid(cls, expense, user, payment_method=None, reference='', comments=''):
        """
        Marks the expense as PAID and posts the GL entry:
            DR <category expense account>
            CR <cash / bank / momo account>
        """
        if expense.status != 'APPROVED':
            raise ValueError(f"Cannot mark paid: expense is {expense.status}.")

        if payment_method:
            expense.payment_method = payment_method
        if reference:
            expense.reference = reference

        # Post to GL first
        je = cls._post_to_gl(expense, user)
        expense.journal_entry = je

        expense.status = 'PAID'
        expense.paid_by = user
        expense.paid_at = timezone.now()
        expense.save(update_fields=[
            'status', 'paid_by', 'paid_at', 'payment_method',
            'reference', 'journal_entry', 'updated_at',
        ])

        ExpenseApproval.objects.create(
            expense=expense, action='PAID', user=user, comments=comments,
        )
        return expense

    # ============================================================
    # GL posting
    # ============================================================
    @staticmethod
    def _resolve_payment_account(payment_method):
        """Cash/Bank/MoMo account to credit when paying."""
        return {
            'CASH': '1010',
            'BANK': '1020',
            'MTN_MOMO': '1030',
            'AIRTEL_MONEY': '1030',
        }.get(payment_method, '1010')

    @classmethod
    def _post_to_gl(cls, expense, user):
        """
        DR <expense account>   (from category)
        CR <cash/bank/momo>    (from payment_method)
        """
        org = expense.organization
        expense_account = expense.category.gl_account
        credit_account_code = cls._resolve_payment_account(expense.payment_method)

        lines = [
            {
                'account_code': expense_account.code,
                'debit': expense.amount,
                'memo': f'{expense.category.name} - {expense.payee}',
            },
            {
                'account_code': credit_account_code,
                'credit': expense.amount,
                'memo': f'Paid via {expense.payment_method}',
            },
        ]

        je = AccountingService.create_journal_entry(
            organization=org,
            entry_date=expense.expense_date,
            reference=expense.expense_number,
            description=f'Expense: {expense.description[:80]}',
            lines=lines,
            source_type='Expense',
            source_id=expense.id,
            branch=expense.branch,
            user=user,
        )
        return je