# apps/payroll/views_pages.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.permissions import IsHRPayroll
from django.utils.decorators import method_decorator
from apps.payroll.models import PayrollRun, Payslip, StaffProfile
from apps.payroll.services import PayrollService
from django.utils import timezone
import datetime

def _check_hr_access(request):
    """Helper to check if user has HR access."""
    if not request.user.is_authenticated:
        return False
    return request.user.role in ['HR_PAYROLL', 'HQ_ADMIN'] or request.user.is_superuser

@login_required
def payroll_dashboard(request):
    """Main HR dashboard showing recent runs and stats."""
    if not _check_hr_access(request):
        messages.error(request, "You do not have permission to access Payroll.")
        return redirect('ui-dashboard')

    org = request.user.organization
    recent_runs = PayrollRun.objects.filter(organization=org).order_by('-month')[:5]
    total_staff = StaffProfile.objects.filter(user__organization=org).count()
    
    context = {
        'recent_runs': recent_runs,
        'total_staff': total_staff,
        'breadcrumbs': [
            {'label': 'Admin', 'href': None},
            {'label': 'Payroll & HR', 'href': None},
        ]
    }
    return render(request, 'app/payroll/dashboard.html', context)

@login_required
def payroll_runs_list(request):
    """List all payroll runs."""
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
        
    org = request.user.organization
    runs = PayrollRun.objects.filter(organization=org).order_by('-month')
    
    return render(request, 'app/payroll/runs_list.html', {
        'runs': runs,
        'breadcrumbs': [
            {'label': 'Admin', 'href': None},
            {'label': 'Payroll', 'href': '/app/payroll/'},
            {'label': 'Runs', 'href': None},
        ]
    })

@login_required
def payroll_run_create(request):
    """Create a new payroll run."""
    if not _check_hr_access(request) or request.method != 'POST':
        return redirect('payroll-runs')
        
    month_str = request.POST.get('month') # expected format: YYYY-MM
    if month_str:
        try:
            # Convert to first day of the month
            month_date = datetime.datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
            org = request.user.organization
            
            run, created = PayrollRun.objects.get_or_create(
                organization=org,
                month=month_date,
                defaults={'status': 'DRAFT'}
            )
            if created:
                messages.success(request, f"Payroll run for {month_date.strftime('%B %Y')} created.")
            else:
                messages.warning(request, f"Payroll run for {month_date.strftime('%B %Y')} already exists.")
                
            return redirect('payroll-run-detail', pk=run.id)
        except ValueError:
            messages.error(request, "Invalid date format.")
            
    return redirect('payroll-runs')

@login_required
def payroll_run_detail(request, pk):
    """View a specific payroll run and process it."""
    if not _check_hr_access(request):
        return redirect('ui-dashboard')
        
    org = request.user.organization
    run = get_object_or_404(PayrollRun, id=pk, organization=org)
    
    # Check if we need to process the run
    if request.method == 'POST' and request.POST.get('action') == 'process':
        if run.status == 'COMPLETED':
            messages.error(request, "This payroll run has already been processed.")
        else:
            try:
                PayrollService.generate_payslips(run)
                messages.success(request, "Payroll processed successfully! Payslips generated.")
            except Exception as e:
                messages.error(request, f"Error processing payroll: {str(e)}")
        return redirect('payroll-run-detail', pk=run.id)

    payslips = run.payslips.all().order_by('staff__first_name')
    
    # Calculate totals
    total_gross = sum(p.total_gross_pay for p in payslips)
    total_net = sum(p.net_pay for p in payslips)

    return render(request, 'app/payroll/run_detail.html', {
        'run': run,
        'payslips': payslips,
        'total_gross': total_gross,
        'total_net': total_net,
        'breadcrumbs': [
            {'label': 'Admin', 'href': None},
            {'label': 'Payroll', 'href': '/app/payroll/'},
            {'label': 'Runs', 'href': '/app/payroll/runs/'},
            {'label': run.month.strftime('%B %Y'), 'href': None},
        ]
    })