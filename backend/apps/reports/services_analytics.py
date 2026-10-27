# apps/reports/services_analytics.py
"""
Report computations for Phase AA analytics.
All functions accept an organization and return JSON-serializable dicts/lists.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.loans.models import Loan, LoanInstallment
from apps.payments.models import Payment, PaymentAllocation
from apps.clients.models import Client
from apps.core.models import User


def _dec(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal('0')


def _f(v):
    return float(v or 0)


def _month_range(start, end):
    """Yield dates for the 1st of each month between start and end."""
    current = start.replace(day=1)
    while current <= end:
        yield current
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def _next_month(d):
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


# ============================================================
# 1. Loan Officer Performance
# ============================================================
def loan_officer_performance(org, from_date, to_date, branch_id=None):
    officers = User.objects.filter(
        organization=org,
        role__in=['LOAN_OFFICER', 'BRANCH_MANAGER', 'HQ_ADMIN'],
        is_active=True,
    )
    if branch_id:
        officers = officers.filter(branch_id=branch_id)

    today = timezone.now().date()
    cutoff_30 = today - timedelta(days=30)

    result = []
    for officer in officers:
        base_loans = Loan.objects.filter(organization=org, loan_officer=officer)

        disbursed_qs = base_loans.filter(
            status__in=['DISBURSED', 'ACTIVE', 'CLOSED'],
            start_date__gte=from_date,
            start_date__lte=to_date,
        )
        disbursed_count = disbursed_qs.count()
        disbursed_value = disbursed_qs.aggregate(s=Sum('disbursed_amount'))['s'] or 0

        active_count = base_loans.filter(
            status__in=['DISBURSED', 'ACTIVE'],
            is_fully_repaid=False,
        ).count()

        portfolio = base_loans.filter(is_fully_repaid=False).aggregate(
            s=Sum('balance_due'))['s'] or 0

        collections = Payment.objects.filter(
            organization=org,
            received_by=officer,
            received_at__date__gte=from_date,
            received_at__date__lte=to_date,
            is_reversed=False,
        ).aggregate(s=Sum('amount'))['s'] or 0

        par_loans = base_loans.filter(
            is_fully_repaid=False,
            installments__is_paid=False,
            installments__due_date__lt=cutoff_30,
        ).distinct()
        par_outstanding = par_loans.aggregate(s=Sum('balance_due'))['s'] or 0
        par_ratio = (_f(par_outstanding) / _f(portfolio) * 100) if portfolio else 0

        new_clients = Client.objects.filter(
            organization=org,
            created_by=officer,
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        ).count()

        result.append({
            'officer_id': str(officer.id),
            'officer_name': officer.get_full_name() or officer.username,
            'role': officer.role,
            'branch_code': officer.branch.code if officer.branch else '--',
            'loans_disbursed': disbursed_count,
            'disbursed_value': _f(disbursed_value),
            'active_loans': active_count,
            'portfolio': _f(portfolio),
            'collected_in_period': _f(collections),
            'par_30_ratio': round(par_ratio, 2),
            'par_outstanding': _f(par_outstanding),
            'new_clients': new_clients,
            'avg_loan_size': (_f(disbursed_value) / disbursed_count) if disbursed_count else 0,
        })

    result.sort(key=lambda r: r['disbursed_value'], reverse=True)
    return {
        'from': from_date.isoformat(),
        'to': to_date.isoformat(),
        'officers': result,
        'totals': {
            'loans_disbursed': sum(r['loans_disbursed'] for r in result),
            'disbursed_value': sum(r['disbursed_value'] for r in result),
            'collected_in_period': sum(r['collected_in_period'] for r in result),
            'portfolio': sum(r['portfolio'] for r in result),
            'new_clients': sum(r['new_clients'] for r in result),
        },
    }


# ============================================================
# 2. Aging Analysis
# ============================================================
def aging_analysis(org, as_of, branch_id=None):
    base_qs = LoanInstallment.objects.filter(
        loan__organization=org,
        loan__is_fully_repaid=False,
        is_paid=False,
    ).select_related('loan')

    if branch_id:
        base_qs = base_qs.filter(loan__branch_id=branch_id)

    buckets = {
        'current':    {'label': 'Current',   'installments': 0, 'principal': Decimal('0'), 'total': Decimal('0'), 'loans': set()},
        'par_1_30':   {'label': 'PAR 1-30',  'installments': 0, 'principal': Decimal('0'), 'total': Decimal('0'), 'loans': set()},
        'par_31_60':  {'label': 'PAR 31-60', 'installments': 0, 'principal': Decimal('0'), 'total': Decimal('0'), 'loans': set()},
        'par_61_90':  {'label': 'PAR 61-90', 'installments': 0, 'principal': Decimal('0'), 'total': Decimal('0'), 'loans': set()},
        'par_90_plus':{'label': 'PAR 90+',   'installments': 0, 'principal': Decimal('0'), 'total': Decimal('0'), 'loans': set()},
    }

    for inst in base_qs.iterator():
        remaining = _dec(inst.total_due) - _dec(inst.paid_amount)
        if remaining <= 0:
            continue
        if inst.due_date > as_of:
            key = 'current'
        else:
            dpd = (as_of - inst.due_date).days
            if dpd <= 30:
                key = 'par_1_30'
            elif dpd <= 60:
                key = 'par_31_60'
            elif dpd <= 90:
                key = 'par_61_90'
            else:
                key = 'par_90_plus'

        buckets[key]['installments'] += 1
        buckets[key]['total'] += remaining
        buckets[key]['principal'] += _dec(inst.principal_amount)
        buckets[key]['loans'].add(inst.loan_id)

    total_outstanding = sum(b['total'] for b in buckets.values())

    rows = []
    for key in ['current', 'par_1_30', 'par_31_60', 'par_61_90', 'par_90_plus']:
        b = buckets[key]
        rows.append({
            'bucket': key,
            'label': b['label'],
            'installments': b['installments'],
            'loans': len(b['loans']),
            'outstanding': _f(b['total']),
            'principal': _f(b['principal']),
            'pct': round(_f(b['total']) / _f(total_outstanding) * 100, 2) if total_outstanding else 0,
        })

    par_outstanding = sum(r['outstanding'] for r in rows if r['bucket'] != 'current')
    par_ratio = (par_outstanding / _f(total_outstanding) * 100) if total_outstanding else 0

    return {
        'as_of': as_of.isoformat(),
        'total_outstanding': _f(total_outstanding),
        'par_outstanding': par_outstanding,
        'par_ratio': round(par_ratio, 2),
        'rows': rows,
    }


# ============================================================
# 3. Portfolio Movement
# ============================================================
def portfolio_movement(org, months=12, branch_id=None):
    end = timezone.now().date()
    start = end - timedelta(days=months * 31)
    start = start.replace(day=1)

    loans_qs = Loan.objects.filter(
        organization=org,
        status__in=['DISBURSED', 'ACTIVE', 'CLOSED'],
    )
    payments_qs = Payment.objects.filter(organization=org, is_reversed=False)
    if branch_id:
        loans_qs = loans_qs.filter(branch_id=branch_id)
        payments_qs = payments_qs.filter(branch_id=branch_id)

    disb = (
        loans_qs.filter(start_date__gte=start, start_date__lte=end)
        .annotate(m=TruncMonth('start_date'))
        .values('m')
        .annotate(total=Sum('disbursed_amount'), count=Count('id'))
    )
    disb_map = {
        r['m'].strftime('%Y-%m'): (_f(r['total']), r['count']) for r in disb
    }

    coll = (
        payments_qs.filter(received_at__date__gte=start, received_at__date__lte=end)
        .annotate(m=TruncMonth('received_at'))
        .values('m')
        .annotate(total=Sum('amount'), count=Count('id'))
    )
    coll_map = {
        r['m'].strftime('%Y-%m'): (_f(r['total']), r['count']) for r in coll
    }

    series = []
    for current in _month_range(start, end):
        key = current.strftime('%Y-%m')
        d_val, d_cnt = disb_map.get(key, (0, 0))
        c_val, c_cnt = coll_map.get(key, (0, 0))
        series.append({
            'month': key,
            'label': current.strftime('%b %Y'),
            'disbursed': d_val,
            'disbursed_count': d_cnt,
            'collected': c_val,
            'collected_count': c_cnt,
            'net': c_val - d_val,
        })

    return {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'months': months,
        'series': series,
        'totals': {
            'disbursed': sum(s['disbursed'] for s in series),
            'collected': sum(s['collected'] for s in series),
            'net': sum(s['net'] for s in series),
            'disbursed_count': sum(s['disbursed_count'] for s in series),
            'collected_count': sum(s['collected_count'] for s in series),
        },
    }


# ============================================================
# 4. Interest Income
# ============================================================
def interest_income_report(org, months=12, branch_id=None):
    end = timezone.now().date()
    start = end - timedelta(days=months * 31)
    start = start.replace(day=1)

    inst_qs = LoanInstallment.objects.filter(
        loan__organization=org,
        due_date__gte=start,
        due_date__lte=end,
    )
    alloc_qs = PaymentAllocation.objects.filter(
        payment__organization=org,
        payment__received_at__date__gte=start,
        payment__received_at__date__lte=end,
        payment__is_reversed=False,
    )
    if branch_id:
        inst_qs = inst_qs.filter(loan__branch_id=branch_id)
        alloc_qs = alloc_qs.filter(payment__branch_id=branch_id)

    accr = (
        inst_qs.annotate(m=TruncMonth('due_date'))
        .values('m').annotate(total=Sum('interest_amount'))
    )
    accr_map = {r['m'].strftime('%Y-%m'): _f(r['total']) for r in accr}

    coll = (
        alloc_qs.annotate(m=TruncMonth('payment__received_at'))
        .values('m').annotate(total=Sum('interest_portion'))
    )
    coll_map = {r['m'].strftime('%Y-%m'): _f(r['total']) for r in coll}

    series = []
    cumulative = 0.0
    for current in _month_range(start, end):
        key = current.strftime('%Y-%m')
        a = accr_map.get(key, 0)
        c = coll_map.get(key, 0)
        cumulative += (a - c)
        series.append({
            'month': key,
            'label': current.strftime('%b %Y'),
            'accrued': a,
            'collected': c,
            'net': a - c,
            'cumulative_diff': cumulative,
        })

    return {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'series': series,
        'totals': {
            'accrued': sum(s['accrued'] for s in series),
            'collected': sum(s['collected'] for s in series),
            'net': sum(s['net'] for s in series),
        },
    }


# ============================================================
# 5. New vs Repeat Clients
# ============================================================
def new_vs_repeat_clients(org, months=12, branch_id=None):
    end = timezone.now().date()
    start = end - timedelta(days=months * 31)
    start = start.replace(day=1)

    series = []
    for current in _month_range(start, end):
        nm = _next_month(current)

        loans_qs = Loan.objects.filter(
            organization=org,
            start_date__gte=current,
            start_date__lt=nm,
        )
        if branch_id:
            loans_qs = loans_qs.filter(branch_id=branch_id)

        # Group loans by client, count distinct
        clients_qs = Client.objects.filter(
            organization=org,
            loans__in=loans_qs,
        ).distinct()
        if branch_id:
            clients_qs = clients_qs.filter(branch_id=branch_id)

        new_count = 0
        repeat_count = 0
        for client in clients_qs:
            first_loan = Loan.objects.filter(
                organization=org, client=client,
            ).order_by('start_date').first()
            if not first_loan:
                continue
            if current <= first_loan.start_date < nm:
                new_count += 1
            else:
                repeat_count += 1

        series.append({
            'month': current.strftime('%Y-%m'),
            'label': current.strftime('%b %Y'),
            'new': new_count,
            'repeat': repeat_count,
            'total': new_count + repeat_count,
        })

    return {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'series': series,
        'totals': {
            'new': sum(s['new'] for s in series),
            'repeat': sum(s['repeat'] for s in series),
            'total': sum(s['total'] for s in series),
        },
    }