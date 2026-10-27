# apps/reports/exporters.py
"""
Shared PDF and Excel export builders.

Every report passes:
  - title      (str)          e.g. "Trial Balance"
  - subtitle   (str, opt)     e.g. "As at 30 Sept 2026"
  - org        (dict)         {'name', 'tin', 'address', 'phone', 'email'}
  - headers    (list[str])
  - rows       (list[list])   each row matches headers length
  - totals     (list, opt)    same shape as a row; bolded at bottom
  - notes      (list[str], opt) footer notes
  - column_alignments (list[str], opt) 'left' | 'right' | 'center'

ReportLab uses Latin-1 base-14 fonts, so any Unicode character that
doesn't fit Latin-1 (em-dash, box drawing, etc.) is replaced before
rendering. Excel handles Unicode natively and needs no such treatment.

IMPORTANT: ReportLab's TableStyle accepts ONLY string alignments
('LEFT', 'RIGHT', 'CENTER'). The integer constants TA_LEFT etc. work
for ParagraphStyle but NOT for TableStyle, so we use strings here.
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import FileResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


# ============================================================
# Unicode sanitizer for ReportLab
# ============================================================
# ReportLab's base-14 fonts (Helvetica, Times, Courier) only cover
# Latin-1. Anything outside that crashes with UnicodeEncodeError.
# We map common cases to ASCII equivalents, then strip any remaining
# non-Latin-1 characters as a safety net.
_UNICODE_REPLACEMENTS = {
    '\u2014': '--',    # em-dash
    '\u2013': '-',     # en-dash
    '\u2012': '-',     # figure dash
    '\u2010': '-',     # hyphen
    '\u2011': '-',     # non-breaking hyphen
    '\u00D7': 'x',     # multiplication sign
    '\u2713': 'OK',    # check mark
    '\u2714': 'OK',    # heavy check mark
    '\u2717': 'X',     # ballot X
    '\u2718': 'X',     # heavy ballot X
    '\u2192': '->',    # right arrow
    '\u2190': '<-',    # left arrow
    '\u00B7': '.',     # middle dot
    '\u2022': '-',     # bullet
    '\u2026': '...',   # ellipsis
    '\u2018': "'",     # left single quote
    '\u2019': "'",     # right single quote
    '\u201C': '"',     # left double quote
    '\u201D': '"',     # right double quote
    '\u00A0': ' ',     # non-breaking space
    '\u20AC': 'EUR',
    '\u00A3': 'GBP',
    '\u00A5': 'JPY',
}


def _sanitize(s):
    """
    Convert any string to a ReportLab-safe Latin-1 string.

    1. Apply known replacements for common Unicode punctuation.
    2. Encode to Latin-1, replacing anything still left over.
    """
    if s is None:
        return ''
    text = str(s)
    for src, dst in _UNICODE_REPLACEMENTS.items():
        text = text.replace(src, dst)
    # Final safety net: strip anything not representable in Latin-1
    return text.encode('latin-1', errors='replace').decode('latin-1')


# ============================================================
# Formatters
# ============================================================
def fmt_money(v):
    if v is None or v == '':
        return '--'
    try:
        n = Decimal(str(v))
    except Exception:
        return str(v)
    if n == 0:
        return '--'
    return 'K' + f'{n:,.2f}'


def fmt_money_zero(v):
    """Like fmt_money but shows K0.00 instead of --."""
    if v is None or v == '':
        return 'K0.00'
    try:
        n = Decimal(str(v))
    except Exception:
        return str(v)
    return 'K' + f'{n:,.2f}'


def fmt_date(d):
    if not d:
        return '--'
    if isinstance(d, (date, datetime)):
        return d.strftime('%d %b %Y')
    try:
        return datetime.fromisoformat(str(d)).strftime('%d %b %Y')
    except Exception:
        return str(d)


def today_str():
    return date.today().strftime('%d %B %Y')


# ============================================================
# PDF builder
# ============================================================
def build_pdf_report(
    title,
    org,
    headers,
    rows,
    subtitle=None,
    totals=None,
    notes=None,
    column_alignments=None,
    landscape_layout=False,
):
    """Render a tabular report as a PDF and return a BytesIO buffer."""
    buf = BytesIO()

    page_size = landscape(A4) if landscape_layout else A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=_sanitize(title),
    )

    styles = getSampleStyleSheet()

    # Custom styles — ParagraphStyle uses the TA_* integer constants fine,
    # they're only problematic for TableStyle.
    org_name = ParagraphStyle(
        'OrgName', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=14, leading=17,
        textColor=colors.HexColor('#0A0A0A'),
    )
    org_meta = ParagraphStyle(
        'OrgMeta', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=11,
        textColor=colors.HexColor('#71717A'),
    )
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=colors.HexColor('#0A0A0A'),
        spaceBefore=6, spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontName='Helvetica-Oblique', fontSize=10, leading=13,
        textColor=colors.HexColor('#52525B'),
    )
    note_style = ParagraphStyle(
        'Note', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=11,
        textColor=colors.HexColor('#71717A'),
    )

    story = []

    # ── Header: Org info ──────────────────────────────
    story.append(Paragraph(_sanitize(org.get('name') or 'Nimbus MFI'), org_name))

    meta_parts = []
    if org.get('tin'):
        meta_parts.append(f"TIN: {org['tin']}")
    if org.get('address'):
        meta_parts.append(org['address'])
    if org.get('phone'):
        meta_parts.append(f"Tel: {org['phone']}")
    if org.get('email'):
        meta_parts.append(org['email'])
    if meta_parts:
        story.append(Paragraph(_sanitize(' . '.join(meta_parts)), org_meta))

    story.append(Spacer(1, 8 * mm))

    # ── Report title + subtitle ───────────────────────
    story.append(Paragraph(_sanitize(title), title_style))
    if subtitle:
        story.append(Paragraph(_sanitize(subtitle), subtitle_style))
    story.append(Spacer(1, 4 * mm))

    # ── Table ─────────────────────────────────────────
    table_data = [[_sanitize(h) for h in headers]] + [
        [_sanitize(c) for c in row]
        for row in rows
    ]

    col_align = column_alignments or ['left'] * len(headers)

    # IMPORTANT: ReportLab TableStyle requires STRING alignment values.
    # Using the TA_* integer constants raises `Invalid justification 0`.
    alignment_map = {
        'left':   'LEFT',
        'right':  'RIGHT',
        'center': 'CENTER',
    }

    style_cmds = [
        # Header row
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#0A0A0A')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ALIGN',         (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING',    (0, 0), (-1, 0), 6),

        # Body rows
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING',    (0, 1), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.25, colors.HexColor('#E4E4E7')),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]

    # Per-column alignment for body rows (string values only)
    for i, align in enumerate(col_align):
        style_cmds.append(
            ('ALIGN', (i, 1), (i, -1), alignment_map.get(align, 'LEFT'))
        )

    # Totals row
    if totals:
        row_idx = len(table_data)
        table_data.append([_sanitize(c) for c in totals])
        style_cmds.extend([
            ('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#FAF7F2')),
            ('FONTNAME',   (0, row_idx), (-1, row_idx), 'Helvetica-Bold'),
            ('LINEABOVE',  (0, row_idx), (-1, row_idx), 1, colors.HexColor('#0A0A0A')),
        ])
        for i, align in enumerate(col_align):
            style_cmds.append(
                ('ALIGN', (i, row_idx), (i, row_idx), alignment_map.get(align, 'LEFT'))
            )

    # Alternate row shading
    for i in range(1, len(rows) + 1):
        if i % 2 == 0:
            style_cmds.append(
                ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FAFAFA'))
            )

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    # ── Notes ─────────────────────────────────────────
    if notes:
        story.append(Spacer(1, 6 * mm))
        for note in notes:
            story.append(Paragraph(f"- {_sanitize(note)}", note_style))

    # ── Footer ────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        _sanitize(f"Generated {datetime.now().strftime('%d %b %Y at %H:%M')} . Nimbus MFI Platform"),
        note_style,
    ))

    doc.build(story)
    buf.seek(0)
    return buf


# ============================================================
# Excel builder
# ============================================================
def build_excel_report(title, org, sheets):
    """
    Render a report as an Excel workbook.

    `sheets` is a list of dicts:
        {
            'name': str,
            'headers': [str],
            'rows': [[...]],
            'totals': [...] | None,
            'column_widths': [int] | None,
        }
    """
    wb = Workbook()
    wb.remove(wb.active)  # start with no default sheet

    # Styles
    header_font = Font(bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill('solid', fgColor='0A0A0A')
    totals_font = Font(bold=True, size=10)
    totals_fill = PatternFill('solid', fgColor='FAF7F2')
    title_font = Font(bold=True, size=13)
    subtitle_font = Font(italic=True, size=9, color='52525B')
    border = Border(
        left=Side(style='thin', color='E4E4E7'),
        right=Side(style='thin', color='E4E4E7'),
        top=Side(style='thin', color='E4E4E7'),
        bottom=Side(style='thin', color='E4E4E7'),
    )

    for sheet_def in sheets:
        ws = wb.create_sheet(title=sheet_def['name'][:31])

        # Row 1: Report title
        ws.cell(row=1, column=1, value=title).font = title_font

        # Row 2: Org name
        ws.cell(row=2, column=1, value=org.get('name') or 'Nimbus MFI').font = Font(bold=True, size=10)

        # Row 3: subtitle / org meta
        meta_parts = []
        if org.get('tin'):
            meta_parts.append(f"TIN: {org['tin']}")
        if org.get('address'):
            meta_parts.append(org['address'])
        if sheet_def.get('subtitle'):
            meta_parts.insert(0, sheet_def['subtitle'])
        if meta_parts:
            ws.cell(row=3, column=1, value=' . '.join(meta_parts)).font = subtitle_font

        # Row 4: spacer
        header_row = 5

        # Header row
        headers = sheet_def.get('headers') or []
        for i, h in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=i, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='left', vertical='center')
            cell.border = border

        # Data rows
        rows = sheet_def.get('rows') or []
        for ri, row in enumerate(rows, start=header_row + 1):
            for ci, val in enumerate(row, start=1):
                cell = ws.cell(row=ri, column=ci, value=val)
                cell.border = border
                if isinstance(val, (int, float, Decimal)):
                    cell.alignment = Alignment(horizontal='right')

        # Totals row
        totals = sheet_def.get('totals')
        if totals:
            tr = header_row + len(rows) + 1
            for ci, val in enumerate(totals, start=1):
                cell = ws.cell(row=tr, column=ci, value=val)
                cell.font = totals_font
                cell.fill = totals_fill
                cell.border = border
                if isinstance(val, (int, float, Decimal)):
                    cell.alignment = Alignment(horizontal='right')

        # Column widths
        widths = sheet_def.get('column_widths')
        if widths:
            for i, w in enumerate(widths, start=1):
                ws.column_dimensions[get_column_letter(i)].width = w
        else:
            # Auto-size by counting characters
            for i, h in enumerate(headers, start=1):
                max_len = len(str(h))
                for row in rows:
                    if i - 1 < len(row):
                        max_len = max(max_len, len(str(row[i - 1])))
                ws.column_dimensions[get_column_letter(i)].width = min(max(max_len + 2, 10), 40)

    # Ensure at least one sheet exists
    if not wb.sheetnames:
        wb.create_sheet(title='Report')

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ============================================================
# File response helpers
# ============================================================
def pdf_response(buf, filename_stem):
    filename = f"{filename_stem}-{date.today().isoformat()}.pdf"
    return FileResponse(
        buf, as_attachment=True, filename=filename,
        content_type='application/pdf',
    )


def excel_response(buf, filename_stem):
    filename = f"{filename_stem}-{date.today().isoformat()}.xlsx"
    return FileResponse(
        buf, as_attachment=True, filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ============================================================
# Organization settings helper
# ============================================================
def get_org_info(org):
    """Return a dict of the org's letterhead fields for the report header."""
    try:
        from apps.core.models import OrganizationSettings
        s = OrganizationSettings.objects.filter(organization=org).first()
        if s:
            return {
                'name': s.legal_name or s.trading_name or org.name,
                'tin': s.tin or '',
                'address': s.physical_address or '',
                'phone': s.phone or '',
                'email': s.email or '',
            }
    except Exception:
        pass
    return {
        'name': getattr(org, 'name', 'Nimbus MFI'),
        'tin': '',
        'address': '',
        'phone': '',
        'email': '',
    }