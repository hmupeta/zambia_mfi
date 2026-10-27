from django.contrib import admin
from .models import GLAccount, JournalEntry, JournalLine, LoanLossProvision
from .models import (
    GLAccount, JournalEntry, JournalLine, LoanLossProvision,
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
)


@admin.register(GLAccount)
class GLAccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'organization', 'account_type', 'is_contra', 'is_active']
    list_filter = ['organization', 'account_type', 'is_active', 'is_contra']
    search_fields = ['code', 'name']
    autocomplete_fields = ['organization', 'parent']
    ordering = ['organization', 'code']


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    autocomplete_fields = ['account']
    readonly_fields = ['account', 'debit', 'credit', 'memo']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = [
        'entry_date', 'reference', 'organization', 'branch',
        'source_type', 'is_posted', 'is_reversed', 'created_at',
    ]
    list_filter = ['organization', 'branch', 'source_type', 'is_posted', 'is_reversed']
    search_fields = ['reference', 'description']
    autocomplete_fields = ['organization', 'branch', 'created_by']
    date_hierarchy = 'entry_date'
    inlines = [JournalLineInline]
    readonly_fields = ['id', 'created_at']

    def has_add_permission(self, request):
        return False   # JE's are created by the system

    def has_delete_permission(self, request, obj=None):
        return False   # never delete — reverse instead


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ['journal_entry', 'account', 'debit', 'credit', 'memo']
    list_filter = ['account__organization', 'account__account_type']
    search_fields = ['journal_entry__reference', 'account__code', 'account__name']


@admin.register(LoanLossProvision)
class LoanLossProvisionAdmin(admin.ModelAdmin):
    list_display = [
        'provision_date', 'loan', 'classification', 'days_past_due',
        'outstanding_balance', 'provision_amount', 'provision_movement',
    ]
    list_filter = ['classification', 'provision_date']
    search_fields = ['loan__loan_number', 'loan__client__first_name', 'loan__client__last_name']
    autocomplete_fields = ['loan']
    date_hierarchy = 'provision_date'
    readonly_fields = ['created_at']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'account_number', 'organization', 'branch',
                    'gl_account', 'currency', 'is_active']
    list_filter = ['organization', 'branch', 'is_active', 'currency']
    search_fields = ['bank_name', 'account_number', 'account_name']
    autocomplete_fields = ['organization', 'branch', 'gl_account']


class BankStatementLineInline(admin.TabularInline):
    model = BankStatementLine
    extra = 0
    fields = ['transaction_date', 'description', 'reference',
              'debit', 'credit', 'match_status', 'matched_journal_line']
    readonly_fields = ['match_status', 'matched_journal_line']
    can_delete = True


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'period_from', 'period_to',
                    'opening_balance', 'closing_balance', 'status', 'source']
    list_filter = ['organization', 'status', 'source', 'bank_account']
    search_fields = ['bank_account__account_number', 'bank_account__bank_name']
    autocomplete_fields = ['organization', 'bank_account', 'created_by']
    date_hierarchy = 'period_to'
    inlines = [BankStatementLineInline]


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ['statement', 'transaction_date', 'description',
                    'debit', 'credit', 'match_status']
    list_filter = ['match_status']
    search_fields = ['description', 'reference']
    autocomplete_fields = ['statement', 'matched_journal_line', 'matched_by']


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'as_of_date', 'statement_closing_balance',
                    'gl_closing_balance', 'reconciled_difference',
                    'is_reconciled', 'status']
    list_filter = ['organization', 'status', 'is_reconciled', 'bank_account']
    autocomplete_fields = ['organization', 'bank_account', 'statement', 'completed_by']
    date_hierarchy = 'as_of_date'