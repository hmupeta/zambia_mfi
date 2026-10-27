# apps/reports/views_documents.py
"""
Endpoints that generate printable documents on demand.
"""
from datetime import date, datetime
from decimal import Decimal

from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsAuthenticatedStaff
from apps.payments.models import Payment
from apps.clients.models import Client
from apps.loans.models import Loan
from apps.origination.models import LoanApplication
from apps.reports.exporters import get_org_info
from .documents import (
    build_payment_receipt, build_client_statement,
    build_loan_offer_letter, build_daily_collection_sheet,
)


def _date(s, default=None):
    if not s:
        return default or date.today()
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return default or date.today()


# ============================================================
# 1. Payment Receipt
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def payment_receipt(request, pk):
    try:
        payment = (
            Payment.objects
            .select_related('client', 'loan', 'branch', 'received_by')
            .prefetch_related('allocations__installment')
            .get(id=pk, organization=request.user.organization)
        )
    except Payment.DoesNotExist:
        return Response({'error': 'Payment not found.'}, status=404)

    org_info = get_org_info(payment.organization)
    buf = build_payment_receipt(payment, org_info)

    filename = f'receipt-{payment.payment_number}.pdf'
    return FileResponse(buf, as_attachment=False, filename=filename,
                        content_type='application/pdf')


# ============================================================
# 2. Client Statement
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def client_statement(request, pk):
    try:
        client = Client.objects.get(id=pk, organization=request.user.organization)
    except Client.DoesNotExist:
        return Response({'error': 'Client not found.'}, status=404)

    from_date = _date(request.query_params.get('from'),
                      date.today().replace(day=1))
    to_date = _date(request.query_params.get('to'), date.today())

    loans_data = []
    for loan in client.loans.all().order_by('-created_at'):
        payments = (
            loan.payments
            .filter(received_at__date__gte=from_date,
                    received_at__date__lte=to_date)
            .order_by('received_at')
        )
        loans_data.append({
            'loan': loan,
            'payments': list(payments),
        })

    org_info = get_org_info(client.organization)
    buf = build_client_statement(client, from_date, to_date, org_info, loans_data)

    filename = f'statement-{client.nrc or client.id}-{from_date}-{to_date}.pdf'
    return FileResponse(buf, as_attachment=False, filename=filename,
                        content_type='application/pdf')


# ============================================================
# 3. Loan Offer Letter
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def application_offer_letter(request, pk):
    try:
        application = (
            LoanApplication.objects
            .select_related('client', 'loan_product', 'branch',
                            'decided_by', 'organization')
            .get(id=pk, organization=request.user.organization)
        )
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Application not found.'}, status=404)

    if application.status not in ('APPROVED', 'DISBURSED'):
        return Response(
            {'error': f'Offer letters can only be generated for approved applications. '
                      f'Current status: {application.status}.'},
            status=400,
        )

    org_info = get_org_info(application.organization)
    buf = build_loan_offer_letter(application, org_info)

    filename = f'offer-{application.application_number}.pdf'
    return FileResponse(buf, as_attachment=False, filename=filename,
                        content_type='application/pdf')


# ============================================================
# 4. Daily Collection Sheet
# ============================================================
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def daily_collection_sheet(request):
    """
    GET /api/reports/documents/daily-collection/?date=YYYY-MM-DD&branch=<uuid>
    """
    target_date = _date(request.query_params.get('date'))
    branch_id = request.query_params.get('branch')

    from apps.loans.models import LoanInstallment
    qs = LoanInstallment.objects.filter(
        due_date=target_date,
        loan__organization=request.user.organization,
    ).select_related(
        'loan', 'loan__client', 'loan__loan_officer', 'loan__branch'
    )

    if branch_id:
        qs = qs.filter(loan__branch_id=branch_id)

    rows = []
    total_due = Decimal('0')
    total_paid = Decimal('0')
    total_balance = Decimal('0')

    for inst in qs:
        due = Decimal(inst.total_due or 0)
        paid = Decimal(inst.paid_amount or 0)
        balance = due - paid

        total_due += due
        total_paid += paid
        total_balance += balance

        officer = inst.loan.loan_officer
        rows.append({
            'loan_officer': (
                officer.get_full_name() if officer else '--'
            ),
            'loan_number': inst.loan.loan_number,
            'client_name': f'{inst.loan.client.first_name} {inst.loan.client.last_name}',
            'due': due,
            'paid': paid,
            'balance': balance,
        })

    totals = {
        'due': total_due,
        'paid': total_paid,
        'balance': total_balance,
        'count': len(rows),
    }

    org_info = get_org_info(request.user.organization)
    buf = build_daily_collection_sheet(target_date, org_info, rows, totals)

    filename = f'daily-collection-{target_date}.pdf'
    return FileResponse(buf, as_attachment=False, filename=filename,
                        content_type='application/pdf')