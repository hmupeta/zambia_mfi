# apps/reports/views_analytics.py
"""
Phase AA analytics endpoints — 5 reports + PDF/Excel exports.
"""
from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsAuthenticatedStaff

from apps.reports.exporters import (
    build_pdf_report, build_excel_report,
    pdf_response, excel_response, get_org_info,
    fmt_money, fmt_date,
)
from .services_analytics import (
    loan_officer_performance,
    aging_analysis,
    portfolio_movement,
    interest_income_report,
    new_vs_repeat_clients,
)


def _d(s, default=None):
    if not s:
        return default or date.today()
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return default or date.today()


def _org(request):
    return request.user.organization


def _branch(request):
    return request.query_params.get('branch') or None


# ============================================================
# 1. Loan Officer Performance
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_loan_officers(request):
    from_date = _d(request.query_params.get('from'),
                   date.today().replace(day=1))
    to_date = _d(request.query_params.get('to'), date.today())
    data = loan_officer_performance(_org(request), from_date, to_date, _branch(request))

    fmt = request.query_params.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        headers = ['Officer', 'Branch', 'Disbursed #', 'Disbursed K',
                   'Portfolio K', 'Collected K', 'PAR 30 %', 'New Clients']
        aligns = ['left', 'left', 'right', 'right', 'right', 'right', 'right', 'right']
        rows = []
        for r in data['officers']:
            rows.append([
                r['officer_name'], r['branch_code'],
                str(r['loans_disbursed']),
                fmt_money(r['disbursed_value']),
                fmt_money(r['portfolio']),
                fmt_money(r['collected_in_period']),
                f"{r['par_30_ratio']}%",
                str(r['new_clients']),
            ])
        totals = [
            'TOTAL', '',
            str(data['totals']['loans_disbursed']),
            fmt_money(data['totals']['disbursed_value']),
            fmt_money(data['totals']['portfolio']),
            fmt_money(data['totals']['collected_in_period']),
            '',
            str(data['totals']['new_clients']),
        ]
        title = 'Loan Officer Performance'
        subtitle = f"Period: {fmt_date(from_date)} to {fmt_date(to_date)}"
        stem = f'loan-officers-{from_date.isoformat()}-{to_date.isoformat()}'
        org_info = get_org_info(_org(request))
        if fmt == 'excel':
            buf = build_excel_report(title, org_info, [{
                'name': 'Officers', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals,
                'column_widths': [24, 10, 12, 16, 16, 16, 12, 12],
            }])
            return excel_response(buf, stem)
        buf = build_pdf_report(title, org_info, headers, rows,
                               subtitle=subtitle, totals=totals,
                               column_alignments=aligns, landscape_layout=True)
        return pdf_response(buf, stem)

    return Response(data)


# ============================================================
# 2. Aging Analysis
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_aging(request):
    as_of = _d(request.query_params.get('as_of'), date.today())
    data = aging_analysis(_org(request), as_of, _branch(request))

    fmt = request.query_params.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        headers = ['Bucket', 'Installments', 'Loans', 'Outstanding (K)', 'Principal (K)', '% of Portfolio']
        aligns = ['left', 'right', 'right', 'right', 'right', 'right']
        rows = [[r['label'], str(r['installments']), str(r['loans']),
                 fmt_money(r['outstanding']), fmt_money(r['principal']),
                 f"{r['pct']}%"] for r in data['rows']]
        totals = ['TOTAL', '', '', fmt_money(data['total_outstanding']),
                  '', '100%']
        title = 'Aging Analysis'
        subtitle = f"As at {fmt_date(as_of)} . PAR Ratio: {data['par_ratio']}%"
        stem = f'aging-{as_of.isoformat()}'
        org_info = get_org_info(_org(request))
        if fmt == 'excel':
            buf = build_excel_report(title, org_info, [{
                'name': 'Aging', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals,
                'column_widths': [14, 14, 10, 18, 18, 14],
            }])
            return excel_response(buf, stem)
        buf = build_pdf_report(title, org_info, headers, rows,
                               subtitle=subtitle, totals=totals,
                               column_alignments=aligns)
        return pdf_response(buf, stem)

    return Response(data)


# ============================================================
# 3. Portfolio Movement
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_portfolio_movement(request):
    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    data = portfolio_movement(_org(request), months, _branch(request))

    fmt = request.query_params.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        headers = ['Month', 'Disbursed #', 'Disbursed (K)', 'Collected #',
                   'Collected (K)', 'Net (K)']
        aligns = ['left', 'right', 'right', 'right', 'right', 'right']
        rows = [[s['label'], str(s['disbursed_count']),
                 fmt_money(s['disbursed']), str(s['collected_count']),
                 fmt_money(s['collected']), fmt_money(s['net'])]
                for s in data['series']]
        totals = ['TOTAL', str(data['totals']['disbursed_count']),
                  fmt_money(data['totals']['disbursed']),
                  str(data['totals']['collected_count']),
                  fmt_money(data['totals']['collected']),
                  fmt_money(data['totals']['net'])]
        title = 'Portfolio Movement'
        subtitle = f"{data['from']} to {data['to']}"
        stem = f'portfolio-movement-{data["from"]}-{data["to"]}'
        org_info = get_org_info(_org(request))
        if fmt == 'excel':
            buf = build_excel_report(title, org_info, [{
                'name': 'Movement', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals,
                'column_widths': [14, 12, 16, 12, 16, 16],
            }])
            return excel_response(buf, stem)
        buf = build_pdf_report(title, org_info, headers, rows,
                               subtitle=subtitle, totals=totals,
                               column_alignments=aligns)
        return pdf_response(buf, stem)

    return Response(data)


# ============================================================
# 4. Interest Income
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_interest_income(request):
    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    data = interest_income_report(_org(request), months, _branch(request))

    fmt = request.query_params.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        headers = ['Month', 'Accrued (K)', 'Collected (K)', 'Net (K)', 'Cumulative Diff (K)']
        aligns = ['left', 'right', 'right', 'right', 'right']
        rows = [[s['label'], fmt_money(s['accrued']), fmt_money(s['collected']),
                 fmt_money(s['net']), fmt_money(s['cumulative_diff'])]
                for s in data['series']]
        totals = ['TOTAL', fmt_money(data['totals']['accrued']),
                  fmt_money(data['totals']['collected']),
                  fmt_money(data['totals']['net']), '']
        title = 'Interest Income'
        subtitle = f"{data['from']} to {data['to']}"
        stem = f'interest-income-{data["from"]}-{data["to"]}'
        org_info = get_org_info(_org(request))
        if fmt == 'excel':
            buf = build_excel_report(title, org_info, [{
                'name': 'Interest', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals,
                'column_widths': [14, 16, 16, 16, 20],
            }])
            return excel_response(buf, stem)
        buf = build_pdf_report(title, org_info, headers, rows,
                               subtitle=subtitle, totals=totals,
                               column_alignments=aligns)
        return pdf_response(buf, stem)

    return Response(data)


# ============================================================
# 5. New vs Repeat Clients
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_new_vs_repeat(request):
    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    data = new_vs_repeat_clients(_org(request), months, _branch(request))

    fmt = request.query_params.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        headers = ['Month', 'New Clients', 'Repeat Clients', 'Total', 'Repeat %']
        aligns = ['left', 'right', 'right', 'right', 'right']
        rows = []
        for s in data['series']:
            repeat_pct = (s['repeat'] / s['total'] * 100) if s['total'] else 0
            rows.append([s['label'], str(s['new']), str(s['repeat']),
                         str(s['total']), f'{repeat_pct:.1f}%'])
        total = data['totals']['total']
        repeat_pct = (data['totals']['repeat'] / total * 100) if total else 0
        totals = ['TOTAL', str(data['totals']['new']),
                  str(data['totals']['repeat']), str(total),
                  f'{repeat_pct:.1f}%']
        title = 'New vs Repeat Clients'
        subtitle = f"{data['from']} to {data['to']}"
        stem = f'new-vs-repeat-{data["from"]}-{data["to"]}'
        org_info = get_org_info(_org(request))
        if fmt == 'excel':
            buf = build_excel_report(title, org_info, [{
                'name': 'Clients', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals,
                'column_widths': [14, 14, 14, 12, 12],
            }])
            return excel_response(buf, stem)
        buf = build_pdf_report(title, org_info, headers, rows,
                               subtitle=subtitle, totals=totals,
                               column_alignments=aligns)
        return pdf_response(buf, stem)

    return Response(data)


# ============================================================
# Overview — for hub page
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def analytics_overview(request):
    org = _org(request)
    today = date.today()
    from_m = today.replace(day=1)

    aging = aging_analysis(org, today, _branch(request))
    movement = portfolio_movement(org, 6, _branch(request))
    interest = interest_income_report(org, 6, _branch(request))
    clients = new_vs_repeat_clients(org, 6, _branch(request))
    officers = loan_officer_performance(org, from_m, today, _branch(request))

    return Response({
        'aging': aging,
        'movement': movement,
        'interest': interest,
        'clients': clients,
        'officers_top': officers['officers'][:5],
        'officers_totals': officers['totals'],
    })