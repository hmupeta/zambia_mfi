# apps/payroll/views_pages.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse

from .models import PayrollRun, Payslip, StaffProfile, PayrollPeriod, PayrollSetting
from apps.accounting.models import GLAccount, BankAccount
from .services import PayrollService


def _check_hr_access(request):
    if not request.user.is_authenticated:
        return False
    return request.user.role in ['HR_PAYROLL', 'HQ_ADMIN'] or request.user.is_superuser


def payroll_dashboard(request):
    if not _check_hr_access(request):
        messages.error(request, "You do not have permission to access Payroll.")
        return redirect('ui-dashboard')

    org = request.user.organization
    # Ordered by the new period relationship
    recent_runs = PayrollRun.objects.filter(organization=org).order_by('-period__start_date')[:5]
    total_staff = StaffProfile.objects.filter(user__organization=org).count()
    
    return render(request, 'app/payroll/dashboard.html', {
        'recent_runs': recent_runs,
        'total_staff': total_staff,
        'breadcrumbs': [{'label': 'Admin', 'href': None}, {'label': 'Payroll & HR', 'href': None}]
    })


def payroll_runs_list(request):
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
    org = request.user.organization
    
    runs = PayrollRun.objects.filter(organization=org).order_by('-period__start_date')
    # Pass open periods so the template can populate the "Start a New Run" dropdown
    open_periods = PayrollPeriod.objects.filter(organization=org, is_closed=False)
    
    return render(request, 'app/payroll/runs_list.html', {
        'runs': runs,
        'open_periods': open_periods,
        'breadcrumbs': [{'label': 'Admin', 'href': None}, {'label': 'Payroll', 'href': '/app/payroll/'}, {'label': 'Runs', 'href': None}]
    })


def payroll_run_create(request):
    if not _check_hr_access(request) or request.method != 'POST':
        return redirect('payroll-runs')
    
    period_id = request.POST.get('period_id')
    if period_id:
        org = request.user.organization
        period = get_object_or_404(PayrollPeriod, id=period_id, organization=org)
        
        if period.is_closed:
            messages.error(request, "This payroll period is already closed.")
        else:
            run, created = PayrollRun.objects.get_or_create(
                organization=org, period=period, defaults={'status': 'DRAFT'}
            )
            if created:
                messages.success(request, f"Payroll run for {period.name} created.")
            else:
                messages.warning(request, f"Payroll run for {period.name} already exists.")
            return redirect('payroll-run-detail', pk=run.id)
            
    return redirect('payroll-runs')


def payroll_run_detail(request, pk):
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
    org = request.user.organization
    run = get_object_or_404(PayrollRun, id=pk, organization=org)
    
    if request.method == 'POST' and request.POST.get('action') == 'process':
        if run.status == 'COMPLETED':
            messages.error(request, "This payroll run has already been processed.")
        else:
            try:
                # Passed request.user for the GL Audit Trail
                PayrollService.generate_payslips(run, request.user)
                messages.success(request, "Payroll processed and posted to GL successfully!")
            except Exception as e:
                messages.error(request, f"Error processing payroll: {str(e)}")
        return redirect('payroll-run-detail', pk=run.id)

    payslips = run.payslips.all().order_by('staff__first_name')
    total_gross = sum(p.total_gross_pay for p in payslips)
    total_net = sum(p.net_pay for p in payslips)

    return render(request, 'app/payroll/run_detail.html', {
        'run': run, 'payslips': payslips, 'total_gross': total_gross, 'total_net': total_net,
        'breadcrumbs': [{'label': 'Admin', 'href': None}, {'label': 'Payroll', 'href': '/app/payroll/'}, {'label': 'Runs', 'href': '/app/payroll/runs/'}, {'label': run.period.name, 'href': None}]
    })


# ==========================================
# NEW VIEWS FOR PERIODS, SETTINGS, AND BANK FILES
# ==========================================

def payroll_periods_list(request):
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
    org = request.user.organization
    periods = PayrollPeriod.objects.filter(organization=org).order_by('-start_date')
    
    if request.method == 'POST':
        # Simple creation form
        name = request.POST.get('name')
        start = request.POST.get('start_date')
        end = request.POST.get('end_date')
        pay_date = request.POST.get('payment_date')
        
        PayrollPeriod.objects.create(
            organization=org, name=name, 
            start_date=start, end_date=end, payment_date=pay_date
        )
        messages.success(request, "Payroll Period created.")
        return redirect('payroll-periods')

    return render(request, 'app/payroll/periods.html', {
        'periods': periods,
        'breadcrumbs': [{'label': 'Payroll', 'href': '/app/payroll/'}, {'label': 'Periods', 'href': None}]
    })


def payroll_settings(request):
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
    
    org = request.user.organization
    settings, created = PayrollSetting.objects.get_or_create(organization=org)
    
    if request.method == 'POST':
        settings.salary_expense_account_id = request.POST.get('salary_expense')
        settings.paye_payable_account_id = request.POST.get('paye_payable')
        settings.napsa_payable_account_id = request.POST.get('napsa_payable')
        settings.nhima_payable_account_id = request.POST.get('nhima_payable')
        settings.bank_account_id = request.POST.get('bank_account')
        settings.save()
        messages.success(request, "Payroll Settings updated successfully.")
        return redirect('payroll-settings')

    context = {
        'settings': settings,
        'expense_accounts': GLAccount.objects.filter(organization=org, account_type='EXPENSE', is_active=True),
        'liability_accounts': GLAccount.objects.filter(organization=org, account_type='LIABILITY', is_active=True),
        'bank_accounts': BankAccount.objects.filter(organization=org, is_active=True),
        'breadcrumbs': [{'label': 'Payroll', 'href': '/app/payroll/'}, {'label': 'Settings', 'href': None}]
    }
    return render(request, 'app/payroll/settings.html', context)


def download_bank_file(request, pk):
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
    
    org = request.user.organization
    run = get_object_or_404(PayrollRun, id=pk, organization=org)
    
    if run.status != 'COMPLETED':
        messages.error(request, "You can only download the bank file for a completed payroll run.")
        return redirect('payroll-run-detail', pk=run.id)
        
    return PayrollService.generate_bank_file(run)