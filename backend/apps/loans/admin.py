from django.contrib import admin
from .models import (
    LoanProduct, BranchLoanProduct, LoanGroup,
    LoanGroupMember, Loan, LoanInstallment, LoanProductFee,
)
from .models import GroupMeeting, GroupAttendance, GroupCollection


# ============================================================
# Loan Product + Fees (inline)
# ============================================================
class LoanProductFeeInline(admin.TabularInline):
    model = LoanProductFee
    extra = 1
    fields = [
        'fee_type', 'name', 'calculation_method',
        'amount', 'percentage', 'charge_timing', 'is_active',
    ]
    ordering = ['fee_type', 'name']


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'organization', 'category',
        'min_amount', 'max_amount',
        'interest_rate', 'interest_rate_period',
        'effective_interest_rate',
        'interest_method', 'is_active',
    ]
    list_filter = [
        'organization', 'category', 'interest_method',
        'interest_rate_period', 'repayment_frequency', 'is_active',
    ]
    search_fields = ['code', 'name']
    autocomplete_fields = ['organization']
    readonly_fields = ['id', 'created_at', 'effective_interest_rate']
    inlines = [LoanProductFeeInline]

    fieldsets = (
        ('Identity', {
            'fields': (
                'id', 'organization', 'code', 'name', 'description',
                'category', 'is_active',
            ),
        }),
        ('Amount & Tenure', {
            'fields': (
                'min_amount', 'max_amount',
                'min_tenure_months', 'max_tenure_months',
            ),
        }),
        ('Pricing', {
            'fields': (
                'interest_method',
                'interest_rate', 'interest_rate_period',
                'effective_interest_rate',
                'penalty_rate', 'grace_days',
                'first_installment_grace_days',
            ),
        }),
        ('Schedule', {
            'fields': ('repayment_frequency',),
        }),
        ('Eligibility', {
            'fields': (
                'requires_guarantor', 'requires_collateral', 'allow_group_loan',
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )


@admin.register(LoanProductFee)
class LoanProductFeeAdmin(admin.ModelAdmin):
    list_display = [
        'loan_product', 'fee_type', 'name',
        'calculation_method', 'amount', 'percentage',
        'charge_timing', 'is_active',
    ]
    list_filter = ['fee_type', 'calculation_method', 'charge_timing', 'is_active']
    search_fields = ['loan_product__code', 'loan_product__name', 'name']
    autocomplete_fields = ['loan_product']


# ============================================================
# Branch Loan Product
# ============================================================
@admin.register(BranchLoanProduct)
class BranchLoanProductAdmin(admin.ModelAdmin):
    list_display = ['branch', 'loan_product', 'is_active']
    list_filter = ['is_active', 'branch__organization']
    autocomplete_fields = ['branch', 'loan_product']


# ============================================================
# Loan Group
# ============================================================
@admin.register(LoanGroup)
class LoanGroupAdmin(admin.ModelAdmin):
    list_display = ['group_name', 'organization', 'branch', 'leader', 'created_at']
    list_filter = ['organization', 'branch']
    search_fields = ['group_name', 'leader__first_name', 'leader__last_name']
    autocomplete_fields = ['organization', 'branch', 'leader']


@admin.register(LoanGroupMember)
class LoanGroupMemberAdmin(admin.ModelAdmin):
    list_display = ['loan_group', 'client', 'is_leader']
    list_filter = ['is_leader']
    autocomplete_fields = ['loan_group', 'client']


# ============================================================
# Loan
# ============================================================
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = [
        'loan_number', 'client', 'organization', 'branch',
        'amount', 'balance_due', 'status', 'maturity_date',
    ]
    list_filter = ['organization', 'branch', 'status', 'loan_product', 'repayment_frequency']
    search_fields = [
        'loan_number', 'client__first_name', 'client__last_name', 'client__nrc',
    ]
    autocomplete_fields = [
        'organization', 'branch', 'client', 'loan_product',
        'loan_officer', 'approved_by', 'loan_group',
    ]
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(LoanInstallment)
class LoanInstallmentAdmin(admin.ModelAdmin):
    list_display = [
        'loan', 'installment_no', 'due_date',
        'total_due', 'paid_amount', 'status',
    ]
    list_filter = ['status', 'due_date']
    search_fields = [
        'loan__loan_number',
        'loan__client__first_name',
        'loan__client__last_name',
    ]
    autocomplete_fields = ['loan']
    date_hierarchy = 'due_date'


# ============================================================
# Group Meeting / Attendance / Collection
# ============================================================
@admin.register(GroupMeeting)
class GroupMeetingAdmin(admin.ModelAdmin):
    list_display = [
        'loan_group', 'meeting_number', 'scheduled_date',
        'status', 'attendance_count',
    ]
    list_filter = ['status', 'scheduled_date']
    search_fields = ['loan_group__group_name', 'loan_group__group_code']
    autocomplete_fields = ['loan_group']


@admin.register(GroupCollection)
class GroupCollectionAdmin(admin.ModelAdmin):
    list_display = [
        'collection_number', 'loan_group', 'amount',
        'channel', 'member_count', 'created_at',
    ]
    list_filter = ['channel', 'created_at']
    search_fields = ['collection_number', 'loan_group__group_name']
    autocomplete_fields = ['loan_group', 'meeting', 'created_by']
    readonly_fields = ['id', 'collection_number', 'created_at', 'member_count']