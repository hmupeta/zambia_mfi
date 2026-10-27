# apps/payments/views_admin.py
from decimal import Decimal
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager

# --- ACCOUNTING SERVICE IMPORT ---
from apps.accounting.services import AccountingService

from .models import Payment
from .serializers_admin import (
    PaymentListSerializer,
    PaymentDetailSerializer,
    PaymentCreateSerializer,
    ReversePaymentSerializer,
)
from .services_admin import preview_allocation, record_payment


class PaymentAdminViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.none()
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_method', 'payment_type', 'branch', 'loan', 'client', 'is_reversed']
    search_fields = [
        'payment_number', 'transaction_ref',
        'client__first_name', 'client__last_name', 'client__nrc',
        'loan__loan_number',
    ]
    ordering_fields = ['received_at', 'amount', 'payment_number']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        if self.action == 'retrieve':
            return PaymentDetailSerializer
        return PaymentListSerializer

    def get_permissions(self):
        if self.action in ('create', 'destroy', 'reverse'):
            return [IsAuthenticatedStaff(), IsHQOrBranchManager()]
        return super().get_permissions()

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return Payment.objects.none()

        qs = (
            Payment.objects
            .filter(organization=org)
            .select_related('client', 'loan', 'branch', 'received_by', 'journal_entry')
            .order_by('-received_at')
        )

        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if date_from:
            qs = qs.filter(received_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__date__lte=date_to)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payment, allocated = record_payment(
                loan=data['loan'],
                amount=data['amount'],
                user=request.user,
                payment_method=data.get('payment_method', 'CASH'),
                payment_type=data.get('payment_type', 'INSTALLMENT'),
                transaction_ref=data.get('transaction_ref', ''),
                notes=data.get('notes', ''),
            )
        except Exception as e:
            return Response({'error': f'Payment failed: {e}'}, status=500)

        out = PaymentDetailSerializer(payment, context={'request': request}).data
        out['allocated_amount'] = float(allocated)
        return Response(out, status=201)

    @action(detail=False, methods=['get'])
    def preview(self, request):
        """GET /api/payments/admin/preview/?loan=<id>&amount=<n>"""
        loan_id = request.query_params.get('loan')
        amount = request.query_params.get('amount')
        if not loan_id or not amount:
            return Response({'error': 'loan and amount are required.'}, status=400)

        try:
            amount = Decimal(amount)
        except Exception:
            return Response({'error': 'Invalid amount.'}, status=400)

        from apps.loans.models import Loan
        org = request.user.organization
        try:
            loan = Loan.objects.get(id=loan_id, organization=org)
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found.'}, status=404)

        return Response(preview_allocation(loan, amount))

    @action(detail=False, methods=['get'])
    def stats(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'today': 0, 'week': 0, 'month': 0, 'count_month': 0})

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        base = Payment.objects.filter(organization=org, is_reversed=False)

        def total_since(d):
            return float(base.filter(received_at__date__gte=d).aggregate(
                s=Sum('amount'))['s'] or 0)

        return Response({
            'today': total_since(today),
            'week': total_since(week_start),
            'month': total_since(month_start),
            'count_month': base.filter(received_at__date__gte=month_start).count(),
        })

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payment = self.get_object()

        if payment.is_reversed:
            return Response({'error': 'Payment already reversed.'}, status=400)

        s = ReversePaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reason = s.validated_data['reason']

        try:
            with transaction.atomic():
                # 1. Restore loan and installments
                for alloc in payment.allocations.all():
                    inst = alloc.installment
                    restored = (
                        Decimal(alloc.principal_portion or 0)
                        + Decimal(alloc.interest_portion or 0)
                        + Decimal(alloc.penalty_portion or 0)
                    )
                    inst.paid_amount = max(Decimal('0'), Decimal(inst.paid_amount or 0) - restored)
                    if inst.paid_amount < Decimal(inst.total_due or 0):
                        inst.is_paid = False
                        inst.paid_at = None
                        inst.status = 'PENDING'
                    inst.save(update_fields=['paid_amount', 'is_paid', 'paid_at', 'status'])

                loan = payment.loan
                if loan:
                    loan.balance_due = Decimal(loan.balance_due or 0) + Decimal(payment.amount or 0)
                    loan.is_fully_repaid = False
                    if loan.status == 'CLOSED':
                        loan.status = 'DISBURSED'
                        loan.closed_at = None
                    loan.save(update_fields=[
                        'balance_due', 'is_fully_repaid', 'status',
                        'closed_at', 'updated_at',
                    ])

                # 2. Mark payment as reversed
                payment.is_reversed = True
                payment.reversed_at = timezone.now()
                payment.reversed_by = request.user
                payment.reversal_reason = reason
                payment.save(update_fields=[
                    'is_reversed', 'reversed_at', 'reversed_by', 'reversal_reason',
                ])

                # 3. Post reversal contra-JE
                original_je = payment.journal_entry
                if original_je:
                    reversal_lines = []
                    for line in original_je.lines.all():
                        reversal_lines.append({
                            'account_code': line.account.code,
                            'debit': float(line.credit),
                            'credit': float(line.debit),
                            'memo': f"Reversal: {line.memo or 'Payment reversal'}"
                        })

                    AccountingService.create_journal_entry(
                        organization=payment.organization,
                        entry_date=timezone.now().date(),
                        reference=f"REV-{payment.payment_number}",
                        description=f"Reversal of payment {payment.payment_number}: {reason}",
                        lines=reversal_lines,
                        source_type='Payment Reversal',
                        source_id=payment.id,
                        branch=payment.branch,
                        user=request.user,
                    )
                else:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Payment {payment.payment_number} was reversed, but no "
                        f"original Journal Entry was found. GL will drift."
                    )

                # 4. Update branch wallet — reversal is OUT
                try:
                    from .services_wallet import WalletService
                    WalletService.record_movement(
                        branch=payment.branch,
                        channel=payment.payment_method,
                        amount=payment.amount,
                        direction='OUT',
                        reference=f'REV-{payment.payment_number}',
                        txn_type='TRANSFER_OUT',
                        user=request.user,
                    )
                except Exception as wallet_err:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Wallet reversal update failed for {payment.payment_number}: {wallet_err}"
                    )

        except Exception as e:
            return Response({'error': f'Reversal failed: {e}'}, status=500)

        return Response(PaymentDetailSerializer(payment, context={'request': request}).data)