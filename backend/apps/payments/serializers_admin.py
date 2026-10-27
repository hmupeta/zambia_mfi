# apps/payments/serializers_admin.py
from rest_framework import serializers

from .models import Payment, PaymentAllocation
from apps.clients.models import Client
from apps.core.models import Branch


class PaymentAllocationSerializer(serializers.ModelSerializer):
    installment_no = serializers.IntegerField(source='installment.installment_no', read_only=True)
    installment_due_date = serializers.DateField(source='installment.due_date', read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = [
            'id', 'installment', 'installment_no', 'installment_due_date',
            'principal_portion', 'interest_portion', 'penalty_portion',
            'allocated_at',
        ]


class PaymentListSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_code = serializers.CharField(source='client.nrc', read_only=True, default=None)
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True, default=None)
    branch_code = serializers.CharField(source='branch.code', read_only=True, default=None)
    received_by_name = serializers.SerializerMethodField()
    method_display = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'payment_number', 'amount',
            'payment_method', 'method_display', 'payment_type',
            'transaction_ref', 'received_at',
            'client', 'client_name', 'client_code',
            'loan', 'loan_number',
            'branch', 'branch_code',
            'received_by', 'received_by_name',
            'is_reversed',
        ]

    def get_client_name(self, obj):
        if not obj.client:
            return None
        return f"{obj.client.first_name or ''} {obj.client.last_name or ''}".strip() or obj.client.nrc

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        name = f"{obj.received_by.first_name or ''} {obj.received_by.last_name or ''}".strip()
        return name or obj.received_by.username

    def get_method_display(self, obj):
        return (obj.payment_method or '').replace('_', ' ').title()


class PaymentDetailSerializer(PaymentListSerializer):
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    journal_ref = serializers.CharField(source='journal_entry.reference', read_only=True, default=None)
    reversal_journal_ref = serializers.CharField(
        source='reversal_journal_entry.reference', read_only=True, default=None,
    )
    reversed_by_name = serializers.SerializerMethodField()
    loan_balance = serializers.SerializerMethodField()

    class Meta(PaymentListSerializer.Meta):
        fields = PaymentListSerializer.Meta.fields + [
            'notes',
            'journal_entry', 'journal_ref',
            'allocations',
            'reversed_at', 'reversed_by', 'reversed_by_name',
            'reversal_reason', 'reversal_journal_entry', 'reversal_journal_ref',
            'loan_balance',
        ]

    def get_reversed_by_name(self, obj):
        if not obj.reversed_by:
            return None
        name = f"{obj.reversed_by.first_name or ''} {obj.reversed_by.last_name or ''}".strip()
        return name or obj.reversed_by.username

    def get_loan_balance(self, obj):
        if not obj.loan:
            return None
        return float(obj.loan.balance_due or 0)


class PaymentCreateSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), required=False, allow_null=True,
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = Payment
        fields = [
            'loan', 'client', 'branch',
            'amount', 'payment_method', 'payment_type',
            'transaction_ref', 'notes',
        ]

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError('Amount must be greater than zero.')
        return value

    def validate(self, attrs):
        loan = attrs.get('loan')
        client = attrs.get('client')
        if not loan:
            raise serializers.ValidationError({'loan': 'Loan is required.'})
        if client and loan.client_id != client.id:
            raise serializers.ValidationError(
                {'client': 'Selected client does not own the selected loan.'}
            )
        attrs['client'] = client or loan.client
        attrs['branch'] = attrs.get('branch') or loan.branch
        return attrs


class ReversePaymentSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=500)