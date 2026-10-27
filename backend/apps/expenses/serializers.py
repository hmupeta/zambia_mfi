from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import ExpenseCategory, Expense, ExpenseApproval


# ============================================================
# Expense Category
# ============================================================
class ExpenseCategorySerializer(serializers.ModelSerializer):
    gl_account_code = serializers.CharField(source='gl_account.code', read_only=True)
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at']


# ============================================================
# Expense Approval Log
# ============================================================
class ExpenseApprovalSerializer(serializers.ModelSerializer):
    # `user_name` matches the naming convention used by the other
    # *_by_name fields on the parent Expense serializer.
    user_name = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = ExpenseApproval
        fields = ['id', 'action', 'user', 'user_name', 'comments', 'created_at']
        read_only_fields = fields


# ============================================================
# Expense — read
# ============================================================
class ExpenseSerializer(serializers.ModelSerializer):
    category_code = serializers.CharField(source='category.code', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    branch_code = serializers.CharField(source='branch.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)   # ← ADDED

    organization_code = serializers.CharField(source='organization.code', read_only=True)

    # Renamed from journal_reference → journal_entry_ref to match the UI.
    journal_entry_ref = serializers.SerializerMethodField()

    approval_log = ExpenseApprovalSerializer(many=True, read_only=True)

    submitted_by_name = serializers.CharField(source='submitted_by.username', read_only=True, default=None)
    approved_by_name  = serializers.CharField(source='approved_by.username',  read_only=True, default=None)
    paid_by_name      = serializers.CharField(source='paid_by.username',      read_only=True, default=None)
    created_by_name   = serializers.CharField(source='created_by.username',   read_only=True, default=None)

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'expense_number', 'status',
            'submitted_by', 'submitted_at', 'approved_by', 'approved_at',
            'paid_by', 'paid_at', 'journal_entry', 'created_at', 'updated_at',
        ]

    @extend_schema_field(serializers.CharField)
    def get_journal_entry_ref(self, obj) -> str:
        if obj.journal_entry:
            return obj.journal_entry.reference
        return ''


# ============================================================
# Expense — create
# ============================================================
class ExpenseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            'branch', 'category', 'amount', 'expense_date',
            'payee', 'description', 'payment_method', 'reference',
            'receipt', 'notes',
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def create(self, validated_data):
        from .services import ExpenseService
        user = self.context['request'].user

        validated_data['organization'] = user.organization
        validated_data['created_by'] = user
        validated_data['expense_number'] = ExpenseService.generate_expense_number(
            user.organization,
        )
        return super().create(validated_data)


# ============================================================
# Workflow actions
# ============================================================
class ExpenseActionSerializer(serializers.Serializer):
    """Used for submit / approve / reject / mark_paid."""
    comments = serializers.CharField(required=False, allow_blank=True, default='')
    payment_method = serializers.ChoiceField(
        choices=['CASH', 'MTN_MOMO', 'AIRTEL_MONEY', 'BANK'],
        required=False,
    )
    reference = serializers.CharField(required=False, allow_blank=True, default='')