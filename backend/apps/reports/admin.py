from django.contrib import admin
from .models import DailyBranchStats


@admin.register(DailyBranchStats)
class DailyBranchStatsAdmin(admin.ModelAdmin):
    list_display = [
        'stat_date', 'branch', 'organization',
        'disbursed_amount', 'collections_amount',
        'active_loans', 'overdue_loans', 'par_30',
    ]
    list_filter = ['organization', 'branch']
    search_fields = ['branch__code', 'branch__name']
    autocomplete_fields = ['organization', 'branch']
    date_hierarchy = 'stat_date'
    ordering = ['-stat_date']