from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import (
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
)
# ============================================================
# Unmatched GL Lines (helper for manual-match UIs)
# ============================================================
from .models import JournalLine  # noqa: E402


class BankAccountSerializer(serializers.ModelSerializer):
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    gl_account_code = serializers.CharField(source='gl_account.code', read_only=True)
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = BankAccount
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at']


class BankStatementLineSerializer(serializers.ModelSerializer):
    matched_reference = serializers.SerializerMethodField()
    matched_entry_date = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementLine
        fields = '__all__'
        read_only_fields = [
            'id', 'matched_journal_line', 'match_status',
            'matched_at', 'matched_by',
        ]

    @extend_schema_field(serializers.CharField)
    def get_matched_reference(self, obj) -> str:
        if obj.matched_journal_line:
            return obj.matched_journal_line.journal_entry.reference
        return ''

    @extend_schema_field(serializers.DateField)
    def get_matched_entry_date(self, obj):
        if obj.matched_journal_line:
            return obj.matched_journal_line.journal_entry.entry_date
        return None


class BankStatementSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source='bank_account.bank_name', read_only=True)
    bank_account_number = serializers.CharField(source='bank_account.account_number', read_only=True)
    lines = BankStatementLineSerializer(many=True, read_only=True)
    line_count = serializers.SerializerMethodField()
    unmatched_count = serializers.SerializerMethodField()

    class Meta:
        model = BankStatement
        fields = [
            'id', 'bank_account', 'bank_account_name', 'bank_account_number',
            'period_from', 'period_to',
            'opening_balance', 'closing_balance',
            'source', 'status', 'notes',
            'line_count', 'unmatched_count',
            'lines', 'created_at', 'updated_at',
        ]

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_unmatched_count(self, obj):
        return obj.lines.filter(match_status='UNMATCHED').count()


class BankStatementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatement
        fields = [
            'bank_account', 'period_from', 'period_to',
            'opening_balance', 'closing_balance', 'source',
            'statement_file', 'notes',
        ]

    def validate(self, data):
        if data['period_from'] > data['period_to']:
            raise serializers.ValidationError("period_from must be <= period_to.")
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['organization'] = user.organization
        validated_data['created_by'] = user
        return super().create(validated_data)


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_number = serializers.CharField(
        source='bank_account.account_number', read_only=True,
    )
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = BankReconciliation
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'created_at', 'completed_at', 'completed_by',
        ]


class ManualMatchSerializer(serializers.Serializer):
    statement_line_id = serializers.IntegerField()
    journal_line_id = serializers.IntegerField()


class UnmatchedGLLineSerializer(serializers.ModelSerializer):
    """
    Lightweight view of a JournalLine for match-selection UIs.
    Only exposes the fields the accountant needs to identify the entry.
    """
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    entry_reference = serializers.CharField(
        source='journal_entry.reference', read_only=True,
    )
    entry_date = serializers.DateField(
        source='journal_entry.entry_date', read_only=True,
    )
    entry_description = serializers.CharField(
        source='journal_entry.description', read_only=True,
    )

    class Meta:
        model = JournalLine
        fields = [
            'id',
            'account', 'account_code', 'account_name',
            'entry_reference', 'entry_date', 'entry_description',
            'debit', 'credit', 'memo',
        ]
        read_only_fields = [
            'id', 'account', 'account_code', 'account_name',
            'entry_reference', 'entry_date', 'entry_description',
            'debit', 'credit', 'memo',
        ]