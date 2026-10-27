from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import LoanRestructure, RestructureEvent
from apps.loans.models import Loan


# ============================================================
# Audit log entry
# ============================================================
class RestructureEventSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = RestructureEvent
        fields = ['id', 'action', 'user', 'username', 'comments', 'created_at']
        read_only_fields = fields


# ============================================================
# Read
# ============================================================
class LoanRestructureSerializer(serializers.ModelSerializer):
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    client_name = serializers.SerializerMethodField()
    client_phone = serializers.CharField(source='loan.client.phone', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    proposed_by_name = serializers.CharField(source='proposed_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    journal_reference = serializers.SerializerMethodField()
    events = RestructureEventSerializer(many=True, read_only=True)

    class Meta:
        model = LoanRestructure
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'branch',
            'original_principal', 'original_balance',
            'original_installment_count', 'original_maturity_date',
            'penalties_waived_amount', 'new_installment_amount',
            'status', 'proposed_by', 'proposed_at',
            'approved_by', 'approved_at',
            'rejected_by', 'rejected_at', 'rejection_reason',
            'applied_at', 'journal_entry',
            'created_at', 'updated_at',
        ]

    @extend_schema_field(serializers.CharField)
    def get_client_name(self, obj) -> str:
        return f"{obj.loan.client.first_name} {obj.loan.client.last_name}"

    @extend_schema_field(serializers.CharField)
    def get_journal_reference(self, obj) -> str:
        return obj.journal_entry.reference if obj.journal_entry else ''


# ============================================================
# Create
# ============================================================
class LoanRestructureCreateSerializer(serializers.Serializer):
    loan = serializers.UUIDField()
    restructure_type = serializers.ChoiceField(choices=[
        'EXTEND_TERM', 'REDUCE_AMOUNT', 'MORATORIUM', 'REFINANCE',
    ])
    reason = serializers.ChoiceField(choices=[
        'FINANCIAL_HARDSHIP', 'MEDICAL', 'NATURAL_DISASTER',
        'BUSINESS_DOWNTURN', 'SEASONAL', 'OTHER',
    ])
    reason_notes = serializers.CharField(required=False, allow_blank=True, default='')

    new_start_date = serializers.DateField()
    new_maturity_date = serializers.DateField()
    new_installment_count = serializers.IntegerField(min_value=1, max_value=200)
    new_interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    new_repayment_frequency = serializers.ChoiceField(choices=[
        'DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY',
    ])

    waive_penalties = serializers.BooleanField(required=False, default=False)
    moratorium_days = serializers.IntegerField(required=False, default=0, min_value=0, max_value=180)

    def validate(self, data):
        if data['new_start_date'] > data['new_maturity_date']:
            raise serializers.ValidationError(
                "new_start_date must be <= new_maturity_date."
            )
        try:
            loan = Loan.objects.get(pk=data['loan'])
        except Loan.DoesNotExist:
            raise serializers.ValidationError("Loan not found.")
        if loan.status not in ('ACTIVE', 'DISBURSED'):
            raise serializers.ValidationError(
                f"Cannot restructure a loan in {loan.status} status."
            )
        return data


# ============================================================
# Actions
# ============================================================
class RestructureActionSerializer(serializers.Serializer):
    comments = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')