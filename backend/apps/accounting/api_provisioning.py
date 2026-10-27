# apps/accounting/api_provisioning.py

from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsHQAdmin
from apps.core.models import AuditLog

from .services_provisioning import ProvisioningService
from .models import LoanLossProvision


def _parse_as_of(raw):
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _preview_payload(org, as_of):
    """
    Build the preview without writing anything to the database.
    Mirrors the loop in ProvisioningService.run_for_organization but
    skips the update_or_create and the GL posting.
    """
    from apps.loans.models import Loan

    active_loans = Loan.objects.filter(
        organization=org,
        status__in=['ACTIVE', 'DISBURSED'],
    ).select_related('branch', 'client')

    total_outstanding = Decimal('0')
    total_required = Decimal('0')
    total_prior = Decimal('0')
    count = 0
    by_class = {}

    for loan in active_loans:
        dpd = ProvisioningService.compute_days_past_due(loan, as_of)
        classification, rate = ProvisioningService.classify(dpd)
        outstanding = loan.balance_due or Decimal('0')
        new_provision = (outstanding * rate).quantize(Decimal('0.01'))

        prior = (
            loan.provisions
            .filter(provision_date__lt=as_of)
            .order_by('-provision_date')
            .first()
        )
        prior_amount = prior.provision_amount if prior else Decimal('0')

        total_outstanding += outstanding
        total_required += new_provision
        total_prior += prior_amount
        count += 1
        by_class[classification] = by_class.get(classification, 0) + 1

    movement = total_required - total_prior

    return {
        'as_of': as_of.isoformat(),
        'loans_count': count,
        'total_outstanding': str(total_outstanding),
        'current_provision_gl': str(total_prior),
        'required_provision': str(total_required),
        'movement': str(movement),
        'movement_direction': (
            'increase' if movement > 0
            else 'decrease' if movement < 0
            else 'none'
        ),
        'can_post': movement != Decimal('0'),
        'by_classification': by_class,
        'journal_lines': [
            {
                'account': 'Impairment Expense',
                'debit':  str(movement) if movement > 0 else '0.00',
                'credit': '0.00' if movement > 0 else str(-movement),
            },
            {
                'account': 'Loan Loss Provision',
                'debit':  '0.00' if movement > 0 else str(-movement),
                'credit': str(movement) if movement > 0 else '0.00',
            },
        ],
    }


@api_view(['POST'])
@permission_classes([IsHQAdmin])
def provisioning_preview(request):
    """
    POST /api/accounting/provisioning/preview/
    Body: {"as_of": "2026-10-31"}

    Returns a preview of the journal entry that would be posted, without
    posting anything. Safe to call repeatedly.
    """
    org = request.user.organization
    if not org:
        return Response(
            {'error': 'No organization on your user account.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    as_of = _parse_as_of(request.data.get('as_of'))
    if not as_of:
        return Response(
            {'error': 'Invalid as_of date. Expected YYYY-MM-DD.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_preview_payload(org, as_of))


@api_view(['POST'])
@permission_classes([IsHQAdmin])
def provisioning_post(request):
    """
    POST /api/accounting/provisioning/post/
    Body: {"as_of": "2026-10-31", "confirm": true}

    Posts the journal entry. Idempotent: if a LoanLossProvision row for
    this (org, as_of) already has a journal entry, refuses rather than
    double-posting.
    """
    org = request.user.organization
    if not org:
        return Response(
            {'error': 'No organization on your user account.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    as_of = _parse_as_of(request.data.get('as_of'))
    if not as_of:
        return Response(
            {'error': 'Invalid as_of date. Expected YYYY-MM-DD.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not request.data.get('confirm'):
        return Response(
            {'error': 'Set "confirm": true to post the journal entry.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Idempotency guard: refuse to run twice for the same date
    already_posted = LoanLossProvision.objects.filter(
        loan__organization=org,
        provision_date=as_of,
        journal_entry__isnull=False,
    ).exists()
    if already_posted:
        return Response(
            {
                'error': (
                    f'Provisioning for {as_of.isoformat()} has already been '
                    'posted. Reverse it first if you need to re-run.'
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        summary = ProvisioningService.run_for_organization(
            organization=org,
            as_of_date=as_of,
        )
    except Exception as e:
        return Response(
            {'error': f'Provisioning failed: {e}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    AuditLog.objects.create(
        organization=org,
        user=request.user,
        action='PROVISIONING_POSTED',
        entity_type='LoanLossProvision',
        new_values={
            'as_of': as_of.isoformat(),
            'loans_processed': summary['loans_processed'],
            'total_provision': str(summary['total_provision']),
            'total_movement': str(summary['total_movement']),
            'by_classification': summary['by_classification'],
        },
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return Response({
        'ok': True,
        'as_of': as_of.isoformat(),
        'loans_processed': summary['loans_processed'],
        'total_provision': str(summary['total_provision']),
        'total_movement': str(summary['total_movement']),
        'posted_at': timezone.now().isoformat(),
    })