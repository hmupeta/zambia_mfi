from django.contrib import admin
from .models import LoanRestructure, RestructureEvent


class RestructureEventInline(admin.TabularInline):
    model = RestructureEvent
    extra = 0
    can_delete = False
    readonly_fields = ['action', 'user', 'comments', 'created_at']
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LoanRestructure)
class LoanRestructureAdmin(admin.ModelAdmin):
    list_display = [
        'loan', 'restructure_type', 'status',
        'original_balance', 'new_installment_amount',
        'new_installment_count', 'created_at',
    ]
    list_filter = ['status', 'restructure_type', 'reason', 'organization']
    search_fields = ['loan__loan_number', 'loan__client__first_name', 'loan__client__last_name']
    autocomplete_fields = ['organization', 'loan', 'branch',
                           'proposed_by', 'approved_by', 'rejected_by', 'journal_entry']
    readonly_fields = ['id', 'organization', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    inlines = [RestructureEventInline]


@admin.register(RestructureEvent)
class RestructureEventAdmin(admin.ModelAdmin):
    list_display = ['restructure', 'action', 'user', 'created_at']
    list_filter = ['action']
    search_fields = ['restructure__loan__loan_number', 'user__username']
    autocomplete_fields = ['restructure', 'user']
    readonly_fields = ['restructure', 'action', 'user', 'comments', 'created_at']

    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False