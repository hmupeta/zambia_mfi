# apps/payroll/admin.py
from django.contrib import admin
from .models import StaffProfile, CommissionRule, PayrollRun, Payslip, PayrollPeriod, PayrollSetting

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'base_salary', 'napsa_number', 'tin_number')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    autocomplete_fields = ['user']


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = ('organization', 'role', 'percentage_of_disbursed', 'percentage_of_collections')
    list_filter = ('organization', 'role')


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('organization', 'name', 'start_date', 'end_date', 'payment_date', 'is_closed')
    list_filter = ('organization', 'is_closed')
    search_fields = ('name',) # <-- Required for PayrollRunAdmin autocomplete


@admin.register(PayrollSetting)
class PayrollSettingAdmin(admin.ModelAdmin):
    list_display = ('organization', 'salary_expense_account', 'bank_account')
    # If you get an E040 error later, it's because GLAccountAdmin needs search_fields


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0
    readonly_fields = (
        'staff', 'basic_pay', 'commission_pay', 'total_gross_pay', 
        'napsa_deduction', 'nhima_deduction', 'paye_tax', 
        'total_deductions', 'net_pay'
    )
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('organization', 'period', 'status', 'created_at')
    list_filter = ('organization', 'status')
    inlines = [PayslipInline]
    readonly_fields = ('status',)
    autocomplete_fields = ['period'] # <-- Now works because PayrollPeriodAdmin is registered