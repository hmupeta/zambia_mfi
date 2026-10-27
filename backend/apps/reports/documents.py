# apps/reports/documents.py
"""
Printable documents — receipts, statements, offer letters, collection sheets.

Uses ReportLab directly (not the generic exporters) because these documents
have a non-tabular layout with headers, signature lines, and letterhead.
"""
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, HRFlowable, KeepTogether,
)


# ============================================================
# Helpers
# ============================================================
_UNICODE_REPLACEMENTS = {
    '\u2014': '--', '\u2013': '-', '\u2012': '-',
    '\u2010': '-', '\u2011': '-',
    '\u00D7': 'x', '\u2713': 'OK',
    '\u2022': '-', '\u2026': '...',
    '\u2018': "'", '\u2019': "'",
    '\u201C': '"', '\u201D': '"',
    '\u00A0': ' ',
}


def _sanitize(s):
    if s is None:
        return ''
    text = str(s)
    for src, dst in _UNICODE_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode('latin-1', errors='replace').decode('latin-1')


def fmt_money(v):
    if v is None or v == '':
        return 'K 0.00'
    try:
        n = Decimal(str(v))
    except Exception:
        return str(v)
    return 'K ' + f'{n:,.2f}'


def fmt_int_money(v):
    try:
        n = Decimal(str(v or 0))
    except Exception:
        n = Decimal('0')
    return 'K ' + f'{n:,.0f}'


def fmt_date(d):
    if not d:
        return '--'
    if isinstance(d, (date, datetime)):
        return d.strftime('%d %b %Y')
    try:
        return datetime.fromisoformat(str(d)).strftime('%d %b %Y')
    except Exception:
        return str(d)


def amount_in_words(amount):
    """Convert a Decimal to Zambian Kwacha words. E.g. 1234.56 -> 'One Thousand Two Hundred Thirty-Four Kwacha and Fifty-Six Ngwee'."""
    try:
        n = Decimal(str(amount)).quantize(Decimal('0.01'))
    except Exception:
        return ''

    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
            'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
            'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
            'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def spell(x):
        if x == 0:
            return 'Zero'
        if x < 20:
            return ones[x]
        if x < 100:
            return (tens[x // 10] + ('-' + ones[x % 10] if x % 10 else ''))
        if x < 1000:
            return (ones[x // 100] + ' Hundred' +
                    (' ' + spell(x % 100) if x % 100 else ''))
        if x < 1_000_000:
            return (spell(x // 1000) + ' Thousand' +
                    (' ' + spell(x % 1000) if x % 1000 else ''))
        if x < 1_000_000_000:
            return (spell(x // 1_000_000) + ' Million' +
                    (' ' + spell(x % 1_000_000) if x % 1_000_000 else ''))
        return (spell(x // 1_000_000_000) + ' Billion' +
                (' ' + spell(x % 1_000_000_000) if x % 1_000_000_000 else ''))

    whole = int(n)
    ngwee = int((n - whole) * 100)
    parts = []
    if whole:
        parts.append(spell(whole) + ' Kwacha')
    if ngwee:
        parts.append(spell(ngwee) + ' Ngwee')
    if not parts:
        return 'Zero Kwacha'
    return ' '.join(parts) + ' Only'


def _styles():
    base = getSampleStyleSheet()
    return {
        'org': ParagraphStyle(
            'Org', parent=base['Normal'],
            fontName='Helvetica-Bold', fontSize=15, leading=18,
            textColor=colors.HexColor('#0A0A0A'),
        ),
        'org_meta': ParagraphStyle(
            'OrgMeta', parent=base['Normal'],
            fontName='Helvetica', fontSize=8.5, leading=11,
            textColor=colors.HexColor('#71717A'),
        ),
        'doc_title': ParagraphStyle(
            'DocTitle', parent=base['Normal'],
            fontName='Helvetica-Bold', fontSize=18, leading=22,
            alignment=1, textColor=colors.HexColor('#0A0A0A'),
            spaceBefore=4, spaceAfter=2,
        ),
        'doc_sub': ParagraphStyle(
            'DocSub', parent=base['Normal'],
            fontName='Helvetica-Oblique', fontSize=10, leading=13,
            alignment=1, textColor=colors.HexColor('#52525B'),
        ),
        'h2': ParagraphStyle(
            'H2', parent=base['Normal'],
            fontName='Helvetica-Bold', fontSize=11, leading=14,
            textColor=colors.HexColor('#0A0A0A'),
            spaceBefore=8, spaceAfter=4,
        ),
        'body': ParagraphStyle(
            'Body', parent=base['Normal'],
            fontName='Helvetica', fontSize=10, leading=14,
            textColor=colors.HexColor('#0A0A0A'),
        ),
        'small': ParagraphStyle(
            'Small', parent=base['Normal'],
            fontName='Helvetica', fontSize=8.5, leading=11,
            textColor=colors.HexColor('#71717A'),
        ),
        'mono': ParagraphStyle(
            'Mono', parent=base['Normal'],
            fontName='Courier', fontSize=9.5, leading=12,
            textColor=colors.HexColor('#0A0A0A'),
        ),
    }


def _org_header(story, org):
    """Add letterhead block to story."""
    st = _styles()
    story.append(Paragraph(_sanitize(org.get('name') or 'Nimbus MFI'), st['org']))
    parts = []
    if org.get('tin'):
        parts.append(f"TIN: {org['tin']}")
    if org.get('address'):
        parts.append(org['address'])
    if org.get('phone'):
        parts.append(f"Tel: {org['phone']}")
    if org.get('email'):
        parts.append(org['email'])
    if parts:
        story.append(Paragraph(_sanitize(' . '.join(parts)), st['org_meta']))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width='100%', thickness=1,
                            color=colors.HexColor('#0A0A0A')))
    story.append(Spacer(1, 4 * mm))


def _footer(story, extra_line=''):
    st = _styles()
    story.append(Spacer(1, 8 * mm))
    if extra_line:
        story.append(Paragraph(_sanitize(extra_line), st['small']))
    story.append(Paragraph(
        _sanitize(
            f"Generated {datetime.now().strftime('%d %b %Y at %H:%M')} "
            f". Nimbus MFI Platform"
        ),
        st['small'],
    ))


# ============================================================
# 1. PAYMENT RECEIPT
# ============================================================
def build_payment_receipt(payment, org_info):
    """
    Official payment receipt PDF.
    `payment` is a Payment model instance with allocations prefetched.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f'Receipt {payment.payment_number}',
    )
    st = _styles()
    story = []

    _org_header(story, org_info)

    story.append(Paragraph('OFFICIAL RECEIPT', st['doc_title']))
    story.append(Paragraph(
        f'Receipt No: {payment.payment_number}', st['doc_sub']
    ))
    story.append(Spacer(1, 6 * mm))

    # Client & payment info — two column table
    client = payment.client
    client_name = f'{client.first_name} {client.last_name}'.strip()

    info_rows = [
        ['Received From:', _sanitize(client_name)],
        ['NRC / ID No:', _sanitize(client.nrc or '--')],
        ['Phone:', _sanitize(client.phone or '--')],
        ['Payment Date:', fmt_date(payment.received_at)],
        ['Loan Ref:', _sanitize(payment.loan.loan_number if payment.loan else '--')],
        ['Payment Method:', _sanitize(payment.payment_method.replace('_', ' '))],
        ['Transaction Ref:', _sanitize(payment.transaction_ref or '--')],
    ]
    info_table = Table(info_rows, colWidths=[45 * mm, 125 * mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0A0A0A')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6 * mm))

    # Amount box — big and prominent
    amount_val = float(payment.amount or 0)
    amount_rows = [
        ['AMOUNT RECEIVED:', fmt_money(payment.amount)],
        ['In Words:', _sanitize(amount_in_words(payment.amount))],
    ]
    amount_table = Table(amount_rows, colWidths=[45 * mm, 125 * mm])
    amount_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Oblique'),
        ('FONTSIZE', (0, 0), (0, 0), 11),
        ('FONTSIZE', (1, 0), (1, 0), 18),
        ('FONTSIZE', (1, 1), (1, 1), 9.5),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FAF7F2')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FAF7F2')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0A0A0A')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 6 * mm))

    # Allocation breakdown
    story.append(Paragraph('Allocation Breakdown', st['h2']))

    alloc_rows = [['Installment', 'Penalty', 'Interest', 'Principal', 'Total']]
    total_penalty = Decimal('0')
    total_interest = Decimal('0')
    total_principal = Decimal('0')
    for alloc in payment.allocations.all().order_by('installment__installment_no'):
        penalty = Decimal(alloc.penalty_portion or 0)
        interest = Decimal(alloc.interest_portion or 0)
        principal = Decimal(alloc.principal_portion or 0)
        sub = penalty + interest + principal
        total_penalty += penalty
        total_interest += interest
        total_principal += principal
        alloc_rows.append([
            f'#{alloc.installment.installment_no}',
            fmt_money(penalty),
            fmt_money(interest),
            fmt_money(principal),
            fmt_money(sub),
        ])

    alloc_rows.append([
        'TOTAL',
        fmt_money(total_penalty),
        fmt_money(total_interest),
        fmt_money(total_principal),
        fmt_money(payment.amount),
    ])

    alloc_table = Table(alloc_rows,
                        colWidths=[28 * mm, 32 * mm, 32 * mm, 38 * mm, 40 * mm])
    alloc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A0A0A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9.5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FAF7F2')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#0A0A0A')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (0, -1), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E4E4E7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(alloc_table)
    story.append(Spacer(1, 6 * mm))

    # Loan balance snapshot
    if payment.loan:
        bal_rows = [
            ['Loan Amount:', fmt_money(payment.loan.amount)],
            ['Total Due:', fmt_money(payment.loan.total_amount_due)],
            ['Balance After Payment:', fmt_money(payment.loan.balance_due)],
            ['Loan Status:', _sanitize(payment.loan.status)],
        ]
        bal_table = Table(bal_rows, colWidths=[55 * mm, 60 * mm])
        bal_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(bal_table)

    # Signature block
    story.append(Spacer(1, 12 * mm))
    sig_rows = [
        ['', ''],
        ['_________________________', '_________________________'],
        ['Received By: ' + _sanitize(
            payment.received_by.get_full_name() if payment.received_by else '--'
        ), 'Client Signature'],
    ]
    sig_table = Table(sig_rows, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, 1), 9),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica'),
        ('FONTSIZE', (0, 2), (-1, 2), 9.5),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#52525B')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('TOPPADDING', (0, 1), (-1, 1), 16),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 4),
    ]))
    story.append(sig_table)

    # Verification hash
    hash_input = f'{payment.payment_number}|{payment.amount}|{payment.received_at}'.encode()
    verify_hash = hashlib.sha256(hash_input).hexdigest()[:12].upper()
    _footer(story, f'Verification Code: {verify_hash}  .  '
                   f'Keep this receipt as proof of payment.')

    doc.build(story)
    buf.seek(0)
    return buf


# ============================================================
# 2. CLIENT STATEMENT
# ============================================================
def build_client_statement(client, from_date, to_date, org_info, loans_data):
    """
    Client account statement.
    loans_data: list of dicts, each {'loan': Loan, 'payments': [Payment, ...]}
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f'Statement {client.nrc}',
    )
    st = _styles()
    story = []

    _org_header(story, org_info)

    story.append(Paragraph('CLIENT STATEMENT', st['doc_title']))
    story.append(Paragraph(
        f'Period: {fmt_date(from_date)} to {fmt_date(to_date)}',
        st['doc_sub']
    ))
    story.append(Spacer(1, 6 * mm))

    # Client block
    client_rows = [
        ['Client Name:', _sanitize(f'{client.first_name} {client.last_name}')],
        ['NRC / ID:', _sanitize(client.nrc or '--')],
        ['Phone:', _sanitize(client.phone or '--')],
        ['Branch:', _sanitize(client.branch.code if client.branch else '--')],
        ['Statement Date:', fmt_date(date.today())],
    ]
    tbl = Table(client_rows, colWidths=[45 * mm, 125 * mm])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    # Summary box
    total_disbursed = sum(Decimal(str(l['loan'].amount or 0)) for l in loans_data)
    total_paid = Decimal('0')
    total_outstanding = Decimal('0')
    for l in loans_data:
        for p in l['payments']:
            if not p.is_reversed:
                total_paid += Decimal(str(p.amount or 0))
        total_outstanding += Decimal(str(l['loan'].balance_due or 0))

    summary_rows = [
        ['Total Loans', str(len(loans_data))],
        ['Total Disbursed', fmt_money(total_disbursed)],
        ['Total Paid (Period)', fmt_money(total_paid)],
        ['Total Outstanding', fmt_money(total_outstanding)],
    ]
    s_tbl = Table(summary_rows, colWidths=[55 * mm, 55 * mm])
    s_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAF7F2')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0A0A0A')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1, 8 * mm))

    # Per-loan breakdowns
    for entry in loans_data:
        loan = entry['loan']
        payments = entry['payments']

        story.append(Paragraph(
            f'Loan {_sanitize(loan.loan_number)}  .  '
            f'{_sanitize(loan.loan_product.name if loan.loan_product else "")}',
            st['h2']
        ))
        meta_rows = [
            ['Amount', fmt_money(loan.amount)],
            ['Interest', fmt_money(loan.total_interest)],
            ['Total Due', fmt_money(loan.total_amount_due)],
            ['Balance', fmt_money(loan.balance_due)],
            ['Status', _sanitize(loan.status)],
        ]
        meta_tbl = Table(meta_rows, colWidths=[40 * mm, 40 * mm, 40 * mm, 50 * mm])
        meta_tbl.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(meta_tbl)
        story.append(Spacer(1, 3 * mm))

        if payments:
            pay_rows = [['Date', 'Ref', 'Method', 'Amount']]
            for p in payments:
                pay_rows.append([
                    fmt_date(p.received_at),
                    _sanitize(p.payment_number),
                    _sanitize(p.payment_method.replace('_', ' ')),
                    fmt_money(p.amount),
                ])
            p_tbl = Table(pay_rows, colWidths=[35 * mm, 60 * mm, 40 * mm, 35 * mm])
            p_tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A0A0A')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E4E4E7')),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(p_tbl)
        else:
            story.append(Paragraph('No payments in this period.', st['small']))

        story.append(Spacer(1, 6 * mm))

    _footer(story)
    doc.build(story)
    buf.seek(0)
    return buf


# ============================================================
# 3. LOAN OFFER LETTER
# ============================================================
def build_loan_offer_letter(application, org_info):
    """Formal loan offer letter for an approved application."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f'Offer Letter {application.application_number}',
    )
    st = _styles()
    story = []

    _org_header(story, org_info)

    client = application.client
    client_name = f'{client.first_name} {client.last_name}'.strip()

    story.append(Paragraph(
        f'Ref: {_sanitize(application.application_number)}',
        st['small'],
    ))
    story.append(Paragraph(fmt_date(date.today()), st['small']))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(
        f'Dear {_sanitize(client_name)},', st['body']
    ))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f'<b>RE: LOAN OFFER OF {fmt_money(application.requested_amount)}</b>',
        st['h2']
    ))

    body_text = (
        f'We are pleased to inform you that your loan application has been approved. '
        f'Please review the terms and conditions below. By accepting this offer, '
        f'you agree to be bound by the terms set out in the loan agreement.'
    )
    story.append(Paragraph(_sanitize(body_text), st['body']))
    story.append(Spacer(1, 5 * mm))

    # Terms table
    terms = [
        ['Principal Amount:', fmt_money(application.requested_amount)],
        ['Interest Rate:', f'{application.loan_product.interest_rate}% per annum'],
        ['Interest Method:', _sanitize(application.loan_product.interest_method.replace('_', ' ').title())],
        ['Tenure:', f'{application.requested_tenure_months} months'],
        ['Repayment Frequency:', _sanitize(application.requested_repayment_frequency.title())],
        ['First Installment:', '30 days from disbursement'],
        ['Purpose:', _sanitize(application.get_purpose_display() if hasattr(application, 'get_purpose_display') else application.purpose)],
    ]
    t_tbl = Table(terms, colWidths=[65 * mm, 90 * mm])
    t_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E4E4E7')),
    ]))
    story.append(t_tbl)
    story.append(Spacer(1, 6 * mm))

    # Conditions
    story.append(Paragraph('Conditions of Acceptance', st['h2']))
    conditions = [
        '1. You must sign the loan agreement and return it within 7 days.',
        '2. You must present your original National Registration Card (NRC).',
        '3. Any collateral offered must be verified and registered before disbursement.',
        '4. All guarantors must sign the guarantee forms.',
        '5. This offer is valid for 30 days from the date of this letter.',
    ]
    for c in conditions:
        story.append(Paragraph(_sanitize(c), st['body']))
        story.append(Spacer(1, 1 * mm))

    story.append(Spacer(1, 8 * mm))

    # Signature block
    story.append(Paragraph('Yours faithfully,', st['body']))
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph('_' * 50, st['body']))
    approver_name = (
        application.decided_by.get_full_name()
        if application.decided_by else '--'
    )
    story.append(Paragraph(_sanitize(approver_name), st['body']))
    story.append(Paragraph('Authorized Signatory', st['small']))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph('_' * 50, st['body']))
    story.append(Paragraph(_sanitize(client_name), st['body']))
    story.append(Paragraph('Client Acceptance Signature & Date', st['small']))

    _footer(story)
    doc.build(story)
    buf.seek(0)
    return buf


# ============================================================
# 4. DAILY COLLECTION SHEET
# ============================================================
def build_daily_collection_sheet(target_date, org_info, rows, totals):
    """
    Cashier end-of-day collection sheet.
    rows: list of dicts {loan_officer, loan_number, client_name, due, paid, balance}
    totals: dict {due, paid, balance, count}
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f'Daily Collection {target_date}',
    )
    st = _styles()
    story = []

    _org_header(story, org_info)

    story.append(Paragraph('DAILY COLLECTION SHEET', st['doc_title']))
    story.append(Paragraph(f'Date: {fmt_date(target_date)}', st['doc_sub']))
    story.append(Spacer(1, 5 * mm))

    # Data table
    header = ['Officer', 'Loan #', 'Client', 'Due', 'Paid', 'Balance']
    data = [header]
    for r in rows:
        data.append([
            _sanitize(r.get('loan_officer') or '--'),
            _sanitize(r.get('loan_number') or ''),
            _sanitize(r.get('client_name') or ''),
            fmt_money(r.get('due')),
            fmt_money(r.get('paid')),
            fmt_money(r.get('balance')),
        ])

    data.append([
        'TOTAL',
        f"({totals.get('count', 0)} loans)",
        '',
        fmt_money(totals.get('due')),
        fmt_money(totals.get('paid')),
        fmt_money(totals.get('balance')),
    ])

    tbl = Table(data, colWidths=[35 * mm, 32 * mm, 45 * mm, 28 * mm, 28 * mm, 28 * mm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A0A0A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 8.5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 9.5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FAF7F2')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#0A0A0A')),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E4E4E7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))

    # Reconciliation block for cashier
    story.append(Paragraph('Cashier Reconciliation', st['h2']))
    recon = [
        ['Physical Cash Count:', '_________________'],
        ['Physical MoMo Balance:', '_________________'],
        ['Physical Bank Slip:', '_________________'],
        ['System Total (from above):', fmt_money(totals.get('paid'))],
        ['Variance:', '_________________'],
    ]
    r_tbl = Table(recon, colWidths=[70 * mm, 85 * mm])
    r_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#52525B')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(r_tbl)

    story.append(Spacer(1, 12 * mm))
    sig_rows = [
        ['', ''],
        ['_________________________', '_________________________'],
        ['Cashier Signature', 'Branch Manager Signature'],
    ]
    sig_tbl = Table(sig_rows, colWidths=[85 * mm, 85 * mm])
    sig_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, 1), 9),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica'),
        ('FONTSIZE', (0, 2), (-1, 2), 9.5),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#52525B')),
        ('TOPPADDING', (0, 1), (-1, 1), 16),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 4),
    ]))
    story.append(sig_tbl)

    _footer(story)
    doc.build(story)
    buf.seek(0)
    return buf