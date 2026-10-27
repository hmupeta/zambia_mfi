# apps/reports/views.py
import logging
from datetime import timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.loans.models import Loan
from apps.clients.models import Client
from apps.payments.models import Payment
from apps.core.models import Branch
from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin
from apps.core.rbac import scope_queryset_by_branch, is_hq

# --- EXPORTERS ---
from apps.reports.exporters import (
    build_pdf_report,
    build_excel_report,
    pdf_response,
    excel_response,
    get_org_info,
    fmt_money,
)
from django.shortcuts import render
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


# ============================================================
# 1. Branch Dashboard (enhanced)
# ============================================================
@extend_schema(
    summary="Branch dashboard statistics",
    description=(
        "Returns aggregated stats for the user's branch. "
        "HQ admins can pass `?branch_id=<uuid>` to filter any branch."
    ),
    parameters=[
        OpenApiParameter(
            name='branch_id',
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description='(HQ only) Filter by branch UUID',
            required=False,
        ),
    ],
    responses={200: OpenApiTypes.OBJECT},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def branch_dashboard(request):
    user = request.user
    branch_id = request.query_params.get('branch_id') if is_hq(user) else None

    loans = scope_queryset_by_branch(Loan.objects.all(), user)
    clients = scope_queryset_by_branch(Client.objects.all(), user)
    payments = scope_queryset_by_branch(Payment.objects.all(), user)

    if branch_id and is_hq(user):
        loans = loans.filter(branch_id=branch_id)
        clients = clients.filter(branch_id=branch_id)
        payments = payments.filter(branch_id=branch_id)

    # ============================================================
    # Core KPIs
    # ============================================================
    total_loans = loans.count()
    active_loans = loans.filter(status__in=['ACTIVE', 'DISBURSED']).count()
    overdue_loans = loans.filter(
        Q(installments__status='OVERDUE') & Q(is_fully_repaid=False)
    ).distinct().count()

    total_disbursed = loans.filter(
        status__in=['ACTIVE', 'DISBURSED', 'CLOSED']
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_clients = clients.filter(is_active=True).count()
    new_clients_this_month = clients.filter(
        created_at__month=timezone.now().month,
        created_at__year=timezone.now().year,
    ).count()

    cutoff = timezone.now().date() - timedelta(days=30)
    overdue_total = 0
    for loan in loans.filter(is_fully_repaid=False):
        for inst in loan.installments.filter(is_paid=False, due_date__lt=cutoff):
            overdue_total += float(inst.total_due - inst.paid_amount)

    par_30 = (overdue_total / float(total_disbursed) * 100) if total_disbursed else 0

    today_payments = payments.filter(
        received_at__date=timezone.now().date()
    ).aggregate(total=Sum('amount'))['total'] or 0

    # ============================================================
    # Cash Position (sum of BranchWallet channels)
    # ============================================================
    cash_position = 0.0
    try:
        from apps.payments.models import BranchWallet
        wallet_qs = BranchWallet.objects.all()
        if branch_id and is_hq(user):
            wallet_qs = wallet_qs.filter(branch_id=branch_id)
        elif not is_hq(user):
            wallet_qs = wallet_qs.filter(branch__organization=user.organization)
            if getattr(user, 'branch', None):
                wallet_qs = wallet_qs.filter(branch=user.branch)
        agg = wallet_qs.aggregate(
            cash=Sum('cash_balance'),
            momo=Sum('mobile_money_balance'),
            bank=Sum('bank_balance'),
        )
        cash_position = float(
            (agg['cash'] or 0) + (agg['momo'] or 0) + (agg['bank'] or 0)
        )
    except Exception as e:
        logger.warning(f"Cash position aggregation failed: {e}")
        cash_position = 0.0

    # ============================================================
    # Disbursed MTD + Growth %
    # ============================================================
    today = timezone.now().date()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    disbursed_mtd = loans.filter(
        status__in=['DISBURSED', 'ACTIVE', 'CLOSED'],
        start_date__gte=month_start,
        start_date__lte=today,
    ).aggregate(s=Sum('disbursed_amount'))['s'] or 0

    disbursed_last_month = loans.filter(
        status__in=['DISBURSED', 'ACTIVE', 'CLOSED'],
        start_date__gte=last_month_start,
        start_date__lte=last_month_end,
    ).aggregate(s=Sum('disbursed_amount'))['s'] or 0

    if float(disbursed_last_month) > 0:
        growth_pct = (
            (float(disbursed_mtd) - float(disbursed_last_month))
            / float(disbursed_last_month)
        ) * 100
    else:
        growth_pct = 100.0 if float(disbursed_mtd) > 0 else 0.0

    # ============================================================
    # Collection Rate MTD
    # ============================================================
    from apps.loans.models import LoanInstallment
    installments_qs = LoanInstallment.objects.filter(loan__in=loans)

    expected_this_month = installments_qs.filter(
        due_date__gte=month_start,
        due_date__lte=today,
    ).aggregate(s=Sum('total_due'))['s'] or 0

    collected_this_month = payments.filter(
        received_at__date__gte=month_start,
        received_at__date__lte=today,
        is_reversed=False,
    ).aggregate(s=Sum('amount'))['s'] or 0

    if float(expected_this_month) > 0:
        collection_rate_pct = min(
            100.0,
            (float(collected_this_month) / float(expected_this_month)) * 100,
        )
    else:
        collection_rate_pct = 100.0 if float(collected_this_month) == 0 else 0.0

    # ============================================================
    # Applications Pipeline
    # ============================================================
    pipeline = {
        'in_review_count': 0, 'in_review_value': 0.0,
        'approved_count': 0, 'approved_value': 0.0,
    }
    try:
        from apps.origination.models import LoanApplication
        app_qs = LoanApplication.objects.filter(organization=user.organization)
        if branch_id and is_hq(user):
            app_qs = app_qs.filter(branch_id=branch_id)
        elif not is_hq(user) and getattr(user, 'branch', None):
            app_qs = app_qs.filter(branch=user.branch)

        in_review = app_qs.filter(status__in=['SUBMITTED', 'UNDER_REVIEW'])
        approved_pending = app_qs.filter(status='APPROVED')

        pipeline = {
            'in_review_count': in_review.count(),
            'in_review_value': float(
                in_review.aggregate(s=Sum('requested_amount'))['s'] or 0
            ),
            'approved_count': approved_pending.count(),
            'approved_value': float(
                approved_pending.aggregate(s=Sum('requested_amount'))['s'] or 0
            ),
        }
    except Exception as e:
        logger.warning(f"Pipeline aggregation failed: {e}")

    # ============================================================
    # Portfolio Aging
    # ============================================================
    aging_qs = installments_qs.filter(is_paid=False)
    today_d = timezone.now().date()

    portfolio_aging = {
        'current': float(
            aging_qs.filter(due_date__gte=today_d)
            .aggregate(s=Sum('total_due'))['s'] or 0
        ),
        'par_1_30': float(
            aging_qs.filter(
                due_date__lt=today_d,
                due_date__gte=today_d - timedelta(days=30),
            ).aggregate(s=Sum('total_due'))['s'] or 0
        ),
        'par_31_60': float(
            aging_qs.filter(
                due_date__lt=today_d - timedelta(days=30),
                due_date__gte=today_d - timedelta(days=60),
            ).aggregate(s=Sum('total_due'))['s'] or 0
        ),
        'par_61_90': float(
            aging_qs.filter(
                due_date__lt=today_d - timedelta(days=60),
                due_date__gte=today_d - timedelta(days=90),
            ).aggregate(s=Sum('total_due'))['s'] or 0
        ),
        'par_90_plus': float(
            aging_qs.filter(due_date__lt=today_d - timedelta(days=90))
            .aggregate(s=Sum('total_due'))['s'] or 0
        ),
    }

    # ============================================================
    # Response
    # ============================================================
    return Response({
        'branch': user.branch.name if getattr(user, 'branch', None) else 'All Branches',

        # existing
        'total_loans': total_loans,
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'total_disbursed': float(total_disbursed),
        'total_clients': total_clients,
        'new_clients_this_month': new_clients_this_month,
        'par_30': round(par_30, 2),
        'today_collections': float(today_payments),

        # new
        'cash_position': cash_position,
        'disbursed_mtd': float(disbursed_mtd),
        'disbursed_last_month': float(disbursed_last_month),
        'disbursement_growth_pct': round(growth_pct, 1),
        'collection_rate_pct': round(collection_rate_pct, 1),
        'pipeline': pipeline,
        'portfolio_aging': portfolio_aging,
    })


# ============================================================
# 2. Daily Collections Report
# ============================================================
@extend_schema(
    summary="Daily collections by branch",
    description="Returns today's payments grouped by branch, or a specific date if provided.",
    parameters=[
        OpenApiParameter(
            name='date',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Report date (YYYY-MM-DD). Defaults to today.',
            required=False,
        ),
    ],
    responses={200: OpenApiTypes.OBJECT},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def daily_collections_report(request):
    user = request.user
    date_param = request.query_params.get('date')

    payments = scope_queryset_by_branch(Payment.objects.all(), user)
    payments = payments.filter(
        received_at__date=date_param if date_param else timezone.now().date()
    )

    report = payments.values('branch__code', 'branch__name').annotate(
        total_amount=Sum('amount'),
        payment_count=Count('id'),
    ).order_by('-total_amount')

    return Response(list(report))


# ============================================================
# 3. Loan Portfolio Report
# ============================================================
@extend_schema(
    summary="Loan portfolio breakdown by product",
    description="Returns totals per loan product, filtered by the user's branch access.",
    responses={200: OpenApiTypes.OBJECT},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def loan_portfolio_report(request):
    user = request.user
    loans = scope_queryset_by_branch(Loan.objects.all(), user)

    report = loans.values(
        'loan_product__code', 'loan_product__name'
    ).annotate(
        total_loans=Count('id'),
        active_loans=Count('id', filter=Q(status__in=['ACTIVE', 'DISBURSED'])),
        total_amount=Sum('amount'),
        outstanding_balance=Sum('balance_due'),
    ).order_by('-total_amount')

    return Response(list(report))


# ============================================================
# 4. Branch Performance (HQ only)
# ============================================================
@extend_schema(
    summary="Branch performance comparison (HQ only)",
    description="Compares all branches side by side. Only accessible by HQ admins.",
    responses={200: OpenApiTypes.OBJECT},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQAdmin])
def branch_performance(request):
    branches = Branch.objects.all()
    data = []
    for branch in branches:
        loans = Loan.objects.filter(branch=branch)
        active = loans.filter(status__in=['ACTIVE', 'DISBURSED']).count()
        disbursed = loans.aggregate(total=Sum('amount'))['total'] or 0
        overdue = loans.filter(
            is_fully_repaid=False, installments__status='OVERDUE'
        ).distinct().count()
        par = (overdue / active * 100) if active else 0

        data.append({
            'branch': branch.name,
            'branch_code': branch.code,
            'active_loans': active,
            'total_disbursed': float(disbursed),
            'overdue_loans': overdue,
            'par_30': round(par, 2),
        })

    return Response(data)


# ============================================================
# 5. Daily Trend
# ============================================================
@extend_schema(
    summary="Daily trend (disbursements & collections)",
    description=(
        "Returns daily totals for disbursements and collections over the "
        "last N days. Used by the dashboard chart."
    ),
    parameters=[
        OpenApiParameter(
            name='days',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Number of days to include (default 30)',
            required=False,
        ),
        OpenApiParameter(
            name='branch_id',
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description='(HQ only) Filter by branch',
            required=False,
        ),
    ],
    responses={200: OpenApiTypes.OBJECT},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def daily_trend(request):
    """Return daily disbursements + collections for the last N days."""
    from datetime import date, timedelta
    from django.db.models.functions import TruncDate

    user = request.user
    days = int(request.query_params.get('days', 30))
    days = max(1, min(days, 365))

    branch_id = request.query_params.get('branch_id') if is_hq(user) else None
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)

    # ---- Loans (disbursements) ----
    loans_qs = scope_queryset_by_branch(Loan.objects.all(), user).filter(
        status__in=['ACTIVE', 'DISBURSED', 'CLOSED'],
        start_date__gte=start_date,
        start_date__lte=end_date,
    )
    if branch_id:
        loans_qs = loans_qs.filter(branch_id=branch_id)

    disb_rows = (
        loans_qs
        .values(day=TruncDate('start_date'))
        .annotate(total=Sum('disbursed_amount'))
        .order_by('day')
    )
    disbursements_by_day = {
        row['day']: float(row['total'] or 0) for row in disb_rows
    }

    # ---- Payments (collections) ----
    payments_qs = scope_queryset_by_branch(Payment.objects.all(), user).filter(
        received_at__date__gte=start_date,
        received_at__date__lte=end_date,
    )
    if branch_id:
        payments_qs = payments_qs.filter(branch_id=branch_id)

    coll_rows = (
        payments_qs
        .values(day=TruncDate('received_at'))
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    collections_by_day = {
        row['day']: float(row['total'] or 0) for row in coll_rows
    }

    # ---- Build continuous series (fill missing days with 0) ----
    series = []
    current = start_date
    while current <= end_date:
        series.append({
            'date': current.isoformat(),
            'label': current.strftime('%d %b'),
            'disbursed': disbursements_by_day.get(current, 0),
            'collected': collections_by_day.get(current, 0),
        })
        current += timedelta(days=1)

    total_disbursed = sum(row['disbursed'] for row in series)
    total_collected = sum(row['collected'] for row in series)

    return Response({
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'days': days,
        'totals': {
            'disbursed': total_disbursed,
            'collected': total_collected,
        },
        'series': series,
    })


# ============================================================
# 6. Trial Balance Export (PDF / Excel)
# ============================================================
@extend_schema(
    summary="Export Trial Balance",
    description="Generates a Trial Balance report as a PDF or Excel file.",
    parameters=[
        OpenApiParameter(
            name='format', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
            description='Export format: "pdf" or "excel". Defaults to pdf.', required=False,
        ),
        OpenApiParameter(
            name='date', type=OpenApiTypes.DATE, location=OpenApiParameter.QUERY,
            description='As of date (YYYY-MM-DD). Defaults to today.', required=False,
        ),
    ],
    responses={200: OpenApiTypes.BINARY},
    tags=['Reports'],
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def export_trial_balance(request):
    """
    Export Trial Balance.

    NOTE: For the real implementation, use `apps/accounting/views_export.py`
    which pulls live data from AccountingService.trial_balance().
    This stub remains for backward compatibility but should be removed.
    """
    user = request.user
    export_format = request.query_params.get('format', 'pdf').lower()
    as_of_date = request.query_params.get('date')

    # Redirect to real accounting export
    from apps.accounting.services import AccountingService
    from datetime import date as _date

    as_of = _date.fromisoformat(as_of_date) if as_of_date else _date.today()
    org = getattr(user, 'organization', None)
    data = AccountingService.trial_balance(org, as_of)

    headers = ['Code', 'Account', 'Type', 'Debit', 'Credit']
    aligns = ['left', 'left', 'left', 'right', 'right']

    def _rows_of(d):
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ('rows', 'accounts', 'results'):
                if isinstance(d.get(k), list):
                    return d[k]
        return []

    raw = _rows_of(data)
    rows = []
    total_dr = 0
    total_cr = 0

    for r in raw:
        dr = float(r.get('debit') or r.get('total_debit') or 0)
        cr = float(r.get('credit') or r.get('total_credit') or 0)
        total_dr += dr
        total_cr += cr
        rows.append([
            str(r.get('code') or r.get('account_code') or ''),
            str(r.get('name') or r.get('account_name') or ''),
            str(r.get('account_type') or r.get('type') or ''),
            fmt_money(dr),
            fmt_money(cr),
        ])

    totals = ['', 'TOTALS', '', fmt_money(total_dr), fmt_money(total_cr)]
    org_info = get_org_info(org)
    subtitle = f"As at {as_of.strftime('%d %B %Y')}"
    stem = f"trial-balance-{as_of.isoformat()}"

    if export_format == 'excel':
        buf = build_excel_report('Trial Balance', org_info, [{
            'name': 'Trial Balance', 'subtitle': subtitle,
            'headers': headers, 'rows': rows, 'totals': totals,
            'column_widths': [10, 42, 14, 18, 18],
        }])
        return excel_response(buf, stem)

    buf = build_pdf_report(
        'Trial Balance', org_info, headers, rows,
        subtitle=subtitle, totals=totals, column_alignments=aligns,
    )
    return pdf_response(buf, stem)

