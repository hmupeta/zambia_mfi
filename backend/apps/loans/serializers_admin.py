# apps/loans/serializers_admin.py
from datetime import date

from rest_framework import serializers

from .models import Loan, LoanInstallment, PromiseToPay


def _compute_dpd(loan, today=None):
    """Days past due = max overdue days across unpaid installments."""
    today = today or date.today()
    max_dpd = 0
    for inst in loan.installments.all():
        if inst.is_paid or (inst.paid_amount or 0) >= (inst.total_due or 0):
            continue
        if inst.due_date and inst.due_date < today:
            days = (today - inst.due_date).days
            max_dpd = max(max_dpd, days)
    return max_dpd


def _next_due(loan):
    """Return (due_date, amount_remaining) for the earliest unpaid installment."""
    for inst in sorted(loan.installments.all(), key=lambda i: i.due_date or date.max):
        if inst.is_paid or (inst.paid_amount or 0) >= (inst.total_due or 0):
            continue
        remaining = (inst.total_due or 0) - (inst.paid_amount or 0)
        return inst.due_date, remaining
    return None, None


class LoanInstallmentSerializer(serializers.ModelSerializer):
    remaining = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = LoanInstallment
        fields = [
            'id', 'installment_no', 'due_date',
            'principal_amount', 'interest_amount', 'penalty_amount',
            'total_due', 'paid_amount', 'remaining',
            'is_paid', 'paid_at', 'status', 'is_overdue',
        ]

    def get_remaining(self, obj):
        return float((obj.total_due or 0) - (obj.paid_amount or 0))

    def get_is_overdue(self, obj):
        return (
            not obj.is_paid
            and obj.due_date
            and obj.due_date < date.today()
            and (obj.paid_amount or 0) < (obj.total_due or 0)
        )


class LoanListSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_code = serializers.CharField(source='client.nrc', read_only=True, default=None)
    branch_code = serializers.CharField(source='branch.code', read_only=True, default=None)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    product_name = serializers.CharField(source='loan_product.name', read_only=True, default=None)
    officer_name = serializers.SerializerMethodField()
    days_past_due = serializers.SerializerMethodField()
    next_due_date = serializers.SerializerMethodField()
    next_due_amount = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            'id', 'loan_number',
            'client', 'client_name', 'client_code',
            'branch', 'branch_code', 'branch_name',
            'loan_product', 'product_name',
            'loan_officer', 'officer_name',
            'amount', 'disbursed_amount', 'balance_due',
            'total_amount_due', 'total_interest', 'total_penalties',
            'interest_rate', 'interest_method', 'repayment_frequency',
            'start_date', 'maturity_date',
            'status', 'status_display', 'is_fully_repaid',
            'days_past_due', 'next_due_date', 'next_due_amount',
            'created_at', 'closed_at',
        ]

    def get_client_name(self, obj) -> str:
        return f'{obj.client.first_name} {obj.client.last_name}'

    def get_officer_name(self, obj):
        if not obj.loan_officer:
            return None
        name = f"{obj.loan_officer.first_name or ''} {obj.loan_officer.last_name or ''}".strip()
        return name or obj.loan_officer.username

    def get_days_past_due(self, obj):
        if hasattr(obj, '_dpd_cache'):
            return obj._dpd_cache
        return _compute_dpd(obj)

    def get_next_due_date(self, obj):
        d, _ = _next_due(obj)
        return str(d) if d else None

    def get_next_due_amount(self, obj):
        _, amt = _next_due(obj)
        return float(amt) if amt is not None else None

    def get_status_display(self, obj):
        return (obj.status or '').replace('_', ' ').title()


class LoanDetailSerializer(LoanListSerializer):
    installments = LoanInstallmentSerializer(many=True, read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    application_ref = serializers.CharField(
        source='source_application.reference', read_only=True, default=None,
    )
    group_name = serializers.CharField(source='loan_group.group_name', read_only=True, default=None)
    journal_ref = serializers.CharField(
        source='disbursement_journal_entry.reference', read_only=True, default=None,
    )
    active_promise = serializers.SerializerMethodField()

    class Meta(LoanListSerializer.Meta):
        fields = LoanListSerializer.Meta.fields + [
            'disbursement_channel', 'disbursement_ref',
            'approved_by', 'approved_by_name',
            'source_application', 'application_ref',
            'loan_group', 'group_name',
            'disbursement_journal_entry', 'journal_ref',
            'installments', 'updated_at',
            'active_promise',
        ]

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        name = f"{obj.approved_by.first_name or ''} {obj.approved_by.last_name or ''}".strip()
        return name or obj.approved_by.username

    def get_active_promise(self, obj):
        promise = obj.promises.filter(status='PENDING').order_by('promised_date').first()
        if promise:
            return {
                'amount': float(promise.amount),
                'date': str(promise.promised_date),
                'notes': promise.notes
            }
        return None


class PromiseToPaySerializer(serializers.ModelSerializer):
    logged_by_name = serializers.CharField(source='logged_by.get_full_name', read_only=True)

    class Meta:
        model = PromiseToPay
        fields = [
            'id', 'loan', 'amount', 'promised_date', 
            'status', 'notes', 'logged_by', 'logged_by_name', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'logged_by', 'created_at', 'updated_at']