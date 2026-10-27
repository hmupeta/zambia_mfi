from rest_framework import serializers
from .models import GLAccount, JournalEntry, JournalLine, LoanLossProvision
from drf_spectacular.utils import extend_schema_field
from .models import GLAccount, JournalEntry, JournalLine, LoanLossProvision


class GLAccountSerializer(serializers.ModelSerializer):
    parent_code = serializers.CharField(source='parent.code', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = GLAccount
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'account_code', 'account_name', 'debit', 'credit', 'memo']


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = JournalEntry
        fields = '__all__'
        read_only_fields = [
            'id', 'is_posted', 'is_reversed', 'reversed_by',
            'created_at', 'created_by',
        ]


class JournalEntryCreateSerializer(serializers.Serializer):
    """
    Manual journal entry creation.
    Lines is a list of {'account_code', 'debit', 'credit', 'memo'}.
    """
    entry_date = serializers.DateField()
    reference = serializers.CharField(max_length=100)
    description = serializers.CharField()
    branch = serializers.UUIDField(required=False, allow_null=True)
    lines = serializers.ListField(child=serializers.DictField())

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line required.")
        total_dr = sum(float(l.get('debit', 0)) for l in value)
        total_cr = sum(float(l.get('credit', 0)) for l in value)
        if round(total_dr, 2) != round(total_cr, 2):
            raise serializers.ValidationError(
                f"Debits ({total_dr}) must equal credits ({total_cr})."
            )
        return value


class LoanLossProvisionSerializer(serializers.ModelSerializer):
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    client_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source='loan.branch.code', read_only=True)

    class Meta:
        model = LoanLossProvision
        fields = '__all__'

    @extend_schema_field(serializers.CharField)
    def get_client_name(self, obj) -> str:
        return f"{obj.loan.client.first_name} {obj.loan.client.last_name}"