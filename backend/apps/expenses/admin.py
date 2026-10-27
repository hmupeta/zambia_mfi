from django.contrib import admin
from .models import ExpenseCategory, Expense, ExpenseApproval


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'organization', 'gl_account',
                    'requires_approval', 'is_active']
    list_filter = ['organization', 'is_active', 'requires_approval']
    search_fields = ['code', 'name']
    autocomplete_fields = ['organization', 'gl_account']


class ExpenseApprovalInline(admin.TabularInline):
    model = ExpenseApproval
    extra = 0
    can_delete = False
    readonly_fields = ['action', 'user', 'comments', 'created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'expense_number', 'expense_date', 'payee', 'category',
        'amount', 'status', 'organization', 'branch',
    ]
    list_filter = ['status', 'organization', 'branch', 'category', 'payment_method']
    search_fields = ['expense_number', 'payee', 'description', 'reference']
    autocomplete_fields = [
        'organization', 'branch', 'category', 'journal_entry',
        'submitted_by', 'approved_by', 'paid_by', 'created_by',
    ]
    readonly_fields = [
        'id', 'expense_number', 'organization',
        'submitted_at', 'approved_at', 'paid_at',
        'journal_entry', 'created_at', 'updated_at',
    ]
    date_hierarchy = 'expense_date'
    inlines = [ExpenseApprovalInline]


@admin.register(ExpenseApproval)
class ExpenseApprovalAdmin(admin.ModelAdmin):
    list_display = ['expense', 'action', 'user', 'created_at']
    list_filter = ['action']
    search_fields = ['expense__expense_number', 'user__username']
    autocomplete_fields = ['expense', 'user']
    readonly_fields = ['expense', 'action', 'user', 'comments', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False