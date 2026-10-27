# apps/accounting/views_export.py
"""
PDF / Excel export endpoints for financial statements and BoZ returns.

Each view:
    GET /api/accounting/exports/<report>/?format=pdf|excel&<params>

Returns a FileResponse with a properly named file.
"""
from datetime import date
from decimal import Decimal

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.reports.exporters import (
    build_pdf_report, build_excel_report,
    pdf_response, excel_response, get_org_info,
    fmt_money,
)
from .services import AccountingService
from .reports import BoZReportGenerator


# ============================================================
# Helpers
# ============================================================
def _date(s, default=None):
    if not s:
        return default or date.today()
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return default or date.today()


def _rows(data, *keys):
    """Extract list of rows from a dict under any of the candidate keys, or the dict itself if it's a list."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for k in keys:
        v = data.get(k)
        if isinstance(v, list):
            return v
    return []


def _val(row, *keys, default=''):
    for k in keys:
        v = row.get(k)
        if v is not None:
            return v
    return default


def _dec(v):
    try:
        return Decimal(str(v or '0'))
    except Exception:
        return Decimal('0')


def _split_by_type(data, wanted):
    """Split a flat `rows` list by account_type."""
    all_rows = _rows(data, 'rows', 'accounts', 'results')
    return [
        r for r in all_rows
        if str(_val(r, 'account_type', 'type')).upper() == wanted.upper()
    ]


# ============================================================
# TRIAL BALANCE
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def export_trial_balance(request):
    fmt = request.query_params.get('format', 'pdf').lower()
    as_of = _date(request.query_params.get('as_of'))
    org = request.user.organization

    data = AccountingService.trial_balance(org, as_of)
    raw = _rows(data, 'rows', 'accounts', 'results')

    headers = ['Code', 'Account', 'Type', 'Debit', 'Credit']
    aligns  = ['left', 'left', 'left', 'right', 'right']

    rows = []
    total_dr = Decimal('0')
    total_cr = Decimal('0')

    for r in raw:
        dr = _dec(_val(r, 'debit', 'total_debit', 'debit_balance'))
        cr = _dec(_val(r, 'credit', 'total_credit', 'credit_balance'))
        total_dr += dr
        total_cr += cr

        # Try multiple key variations since service output shapes vary
        code = _val(
            r,
            'code', 'account_code', 'account__code', 'gl_code',
        )
        name = _val(
            r,
            'name', 'account_name', 'account__name', 'gl_name',
        )
        acct_type = _val(
            r,
            'account_type', 'type', 'account__type', 'gl_type',
        )

        rows.append([
            str(code) if code not in (None, '') else '',
            str(name) if name not in (None, '') else '',
            str(acct_type) if acct_type not in (None, '') else '',
            fmt_money(dr),
            fmt_money(cr),
        ])

    totals = ['', 'TOTALS', '', fmt_money(total_dr), fmt_money(total_cr)]
    org_info = get_org_info(org)
    subtitle = f"As at {as_of.strftime('%d %B %Y')}"
    stem = f"trial-balance-{as_of.isoformat()}"

    if fmt == 'excel':
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


# ============================================================
# INCOME STATEMENT
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def export_income_statement(request):
    fmt = request.query_params.get('format', 'pdf').lower()
    from_date = _date(request.query_params.get('from'), date.today().replace(day=1))
    to_date = _date(request.query_params.get('to'))
    org = request.user.organization

    data = AccountingService.income_statement(org, from_date, to_date)

    income_rows = _rows(data, 'revenue', 'income', 'revenues')
    expense_rows = _rows(data, 'expenses', 'expense')

    if not income_rows:
        income_rows = _split_by_type(data, 'INCOME')
    if not expense_rows:
        expense_rows = _split_by_type(data, 'EXPENSE')

    headers = ['Code', 'Account', 'Amount']
    aligns  = ['left', 'left', 'right']

    rows = []
    rows.append(['', 'REVENUE', ''])
    rev_total = Decimal('0')
    for r in income_rows:
        amt = _dec(_val(r, 'amount', 'balance'))
        rev_total += amt
        rows.append([
            str(_val(r, 'code', 'account_code', 'account__code')),
            str(_val(r, 'name', 'account_name', 'account__name')),
            fmt_money(amt),
        ])
    rows.append(['', 'Total Revenue', fmt_money(rev_total)])

    rows.append(['', '', ''])
    rows.append(['', 'EXPENSES', ''])
    exp_total = Decimal('0')
    for r in expense_rows:
        amt = _dec(_val(r, 'amount', 'balance'))
        exp_total += amt
        rows.append([
            str(_val(r, 'code', 'account_code', 'account__code')),
            str(_val(r, 'name', 'account_name', 'account__name')),
            fmt_money(amt),
        ])
    rows.append(['', 'Total Expenses', fmt_money(exp_total)])

    net_income = rev_total - exp_total
    totals = ['', 'NET INCOME', fmt_money(net_income)]

    org_info = get_org_info(org)
    subtitle = f"For period {from_date.strftime('%d %b %Y')} — {to_date.strftime('%d %b %Y')}"
    stem = f"income-statement-{from_date.isoformat()}-{to_date.isoformat()}"

    if fmt == 'excel':
        buf = build_excel_report('Income Statement', org_info, [{
            'name': 'Income Statement', 'subtitle': subtitle,
            'headers': headers, 'rows': rows, 'totals': totals,
            'column_widths': [10, 45, 18],
        }])
        return excel_response(buf, stem)

    buf = build_pdf_report(
        'Income Statement (P&L)', org_info, headers, rows,
        subtitle=subtitle, totals=totals, column_alignments=aligns,
    )
    return pdf_response(buf, stem)


# ============================================================
# BALANCE SHEET
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def export_balance_sheet(request):
    fmt = request.query_params.get('format', 'pdf').lower()
    as_of = _date(request.query_params.get('as_of'))
    org = request.user.organization

    data = AccountingService.balance_sheet(org, as_of)

    asset_rows  = _rows(data, 'assets', 'asset')
    liab_rows   = _rows(data, 'liabilities', 'liability')
    equity_rows = _rows(data, 'equity', 'equities')

    if not asset_rows:
        asset_rows = _split_by_type(data, 'ASSET')
    if not liab_rows:
        liab_rows = _split_by_type(data, 'LIABILITY')
    if not equity_rows:
        equity_rows = _split_by_type(data, 'EQUITY')

    # ============================================================
    # FIX: Compute current year net income and add to equity
    # ============================================================
    # Determine fiscal year start (assumes calendar year — adjust if needed)
    fiscal_year_start = as_of.replace(month=1, day=1)

    try:
        pnl = AccountingService.income_statement(org, fiscal_year_start, as_of)
        income_rows  = _rows(pnl, 'revenue', 'income', 'revenues')
        expense_rows = _rows(pnl, 'expenses', 'expense')

        if not income_rows:
            income_rows = _split_by_type(pnl, 'INCOME')
        if not expense_rows:
            expense_rows = _split_by_type(pnl, 'EXPENSE')

        total_income = sum(
            (_dec(_val(r, 'amount', 'balance')) for r in income_rows),
            Decimal('0'),
        )
        total_expense = sum(
            (_dec(_val(r, 'amount', 'balance')) for r in expense_rows),
            Decimal('0'),
        )
        net_income = total_income - total_expense
    except Exception:
        net_income = Decimal('0')

    # Append net income as a synthetic equity line
    equity_rows = list(equity_rows) + [{
        'code': '',
        'name': 'Current Year Net Income',
        'amount': net_income,
    }]
    # ============================================================

    headers = ['Code', 'Account', 'Amount']
    aligns  = ['left', 'left', 'right']

    def section(label, items):
        block = [['', label, '']]
        total = Decimal('0')
        for r in items:
            amt = _dec(_val(r, 'amount', 'balance'))
            total += amt
            block.append([
                str(_val(r, 'code', 'account_code', 'account__code')),
                str(_val(r, 'name', 'account_name', 'account__name')),
                fmt_money(amt),
            ])
        block.append(['', f'Total {label.title()}', fmt_money(total)])
        block.append(['', '', ''])
        return block, total

    rows = []
    a_block, tot_a = section('ASSETS', asset_rows);       rows.extend(a_block)
    l_block, tot_l = section('LIABILITIES', liab_rows);   rows.extend(l_block)
    e_block, tot_e = section('EQUITY', equity_rows);      rows.extend(e_block)

    totals = ['', 'TOTAL LIABILITIES + EQUITY', fmt_money(tot_l + tot_e)]

    # Balance-check footer note
    diff = tot_a - (tot_l + tot_e)
    notes = []
    if abs(diff) < Decimal('0.01'):
        notes.append(f"Balance check: BALANCED (Assets = {fmt_money(tot_a)})")
    else:
        notes.append(
            f"Balance check: OUT OF BALANCE by {fmt_money(diff)} "
            f"(Assets = {fmt_money(tot_a)}, L+E = {fmt_money(tot_l + tot_e)})"
        )

    org_info = get_org_info(org)
    subtitle = f"As at {as_of.strftime('%d %B %Y')}"
    stem = f"balance-sheet-{as_of.isoformat()}"

    if fmt == 'excel':
        excel_rows = list(rows) + [
            ['', '', ''],
            ['', 'TOTAL ASSETS', fmt_money(tot_a)],
        ]
        buf = build_excel_report('Balance Sheet', org_info, [{
            'name': 'Balance Sheet', 'subtitle': subtitle,
            'headers': headers, 'rows': excel_rows, 'totals': totals,
            'column_widths': [10, 45, 18],
        }])
        return excel_response(buf, stem)

    buf = build_pdf_report(
        'Balance Sheet', org_info, headers, rows,
        subtitle=subtitle, totals=totals, notes=notes,
        column_alignments=aligns,
    )
    return pdf_response(buf, stem)


# ============================================================
# NPL RETURN
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQAdmin])
def export_npl_return(request):
    fmt = request.query_params.get('format', 'pdf').lower()
    as_of = _date(request.query_params.get('as_of'))
    org = request.user.organization

    data = BoZReportGenerator.npl_return(org, as_of)
    raw_rows = data.get('rows', [])
    totals = data.get('totals', {})

    headers = ['Branch', 'Loan #', 'Client', 'NRC', 'Product',
               'Outstanding', 'DPD', 'Class', 'Rate', 'Provision']
    aligns  = ['left', 'left', 'left', 'left', 'left',
               'right', 'right', 'left', 'right', 'right']

    rows = []
    for r in raw_rows:
        rate = r.get('provision_rate') or 0
        rows.append([
            str(r.get('branch_code', '')),
            str(r.get('loan_number', '')),
            str(r.get('client_name', '')),
            str(r.get('client_nrc', '')),
            str(r.get('product_code', '')),
            fmt_money(r.get('outstanding_balance')),
            str(r.get('days_past_due', '')),
            str(r.get('classification', '')),
            f"{float(rate) * 100:.1f}%",
            fmt_money(r.get('provision_amount')),
        ])

    totals_row = [
        '', '', '', '', 'TOTALS',
        fmt_money(totals.get('total_outstanding')),
        '', '', '',
        fmt_money(totals.get('total_provision')),
    ]

    notes = [
        f"Total Outstanding: K{float(totals.get('total_outstanding') or 0):,.2f}",
        f"Total Provision:   K{float(totals.get('total_provision') or 0):,.2f}",
        f"NPL Outstanding:   K{float(totals.get('npl_outstanding') or 0):,.2f}",
        f"NPL Provision:     K{float(totals.get('npl_provision') or 0):,.2f}",
        f"NPL Ratio:         {totals.get('npl_ratio_percent', 0)}%",
    ]

    org_info = get_org_info(org)
    subtitle = f"Bank of Zambia NPL Return · As at {as_of.strftime('%d %B %Y')}"
    stem = f"npl-return-{as_of.isoformat()}"

    if fmt == 'excel':
        summary_rows = []
        for cls, s in (data.get('classification_summary') or {}).items():
            summary_rows.append([
                cls.replace('_', ' ').title(),
                s.get('count', 0),
                fmt_money(s.get('outstanding')),
                fmt_money(s.get('provision')),
            ])

        buf = build_excel_report('NPL Return', org_info, [
            {
                'name': 'NPL Schedule', 'subtitle': subtitle,
                'headers': headers, 'rows': rows, 'totals': totals_row,
            },
            {
                'name': 'Classification Summary', 'subtitle': subtitle,
                'headers': ['Classification', 'Count', 'Outstanding', 'Provision'],
                'rows': summary_rows,
                'column_widths': [22, 10, 22, 22],
            },
        ])
        return excel_response(buf, stem)

    buf = build_pdf_report(
        'Non-Performing Loan Return', org_info, headers, rows,
        subtitle=subtitle, totals=totals_row, notes=notes,
        column_alignments=aligns,
        landscape_layout=True,
    )
    return pdf_response(buf, stem)


# ============================================================
# PORTFOLIO AT RISK
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def export_par(request):
    fmt = request.query_params.get('format', 'pdf').lower()
    as_of = _date(request.query_params.get('as_of'))
    org = request.user.organization

    data = BoZReportGenerator.portfolio_at_risk(org, as_of)
    total_portfolio = data.get('total_portfolio', 0)

    headers = ['Bucket', 'Overdue Balance', 'Ratio (%)']
    aligns  = ['left', 'right', 'right']

    labels = [
        ('par_1',  'PAR > 1 day'),
        ('par_7',  'PAR > 7 days'),
        ('par_30', 'PAR > 30 days'),
        ('par_60', 'PAR > 60 days'),
        ('par_90', 'PAR > 90 days'),
    ]

    rows = []
    for key, label in labels:
        bucket = data.get(key) or {}
        rows.append([
            label,
            fmt_money(bucket.get('overdue_balance', 0)),
            f"{bucket.get('ratio_percent', 0)}%",
        ])

    totals = ['Total Portfolio', fmt_money(total_portfolio), '']

    org_info = get_org_info(org)
    subtitle = f"Portfolio at Risk · As at {as_of.strftime('%d %B %Y')}"
    stem = f"par-{as_of.isoformat()}"

    if fmt == 'excel':
        buf = build_excel_report('Portfolio at Risk', org_info, [{
            'name': 'PAR', 'subtitle': subtitle,
            'headers': headers, 'rows': rows, 'totals': totals,
            'column_widths': [30, 22, 14],
        }])
        return excel_response(buf, stem)

    buf = build_pdf_report(
        'Portfolio at Risk', org_info, headers, rows,
        subtitle=subtitle, totals=totals, column_alignments=aligns,
    )
    return pdf_response(buf, stem)