# apps/payments/views.py
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from .models import Payment, PaymentAllocation, BranchWallet, WalletTransaction
from .serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentAllocationSerializer,
    BranchWalletSerializer,
    WalletTransactionSerializer,
)
from .services import PaymentService
from .services_wallet import WalletService
from apps.core.models import Branch
from apps.core.permissions import (
    IsAuthenticatedStaff,
    IsObjectInBranch,
    IsHQAdmin,
    IsBranchStaff,
)
from apps.core.mixins import AuditLogMixin
from apps.core.rbac import scope_queryset_by_branch


# ============================================================
# Payment ViewSet
# ============================================================
class PaymentViewSet(AuditLogMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'Payment'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_method', 'payment_type', 'branch', 'client', 'loan']
    search_fields = ['payment_number', 'client__first_name', 'client__last_name', 'client__nrc']
    ordering_fields = ['received_at', 'amount']

    def get_queryset(self):
        qs = scope_queryset_by_branch(Payment.objects.all(), self.request.user)
        
        # Filter by date range for the Reports Hub
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            qs = qs.filter(received_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__date__lte=date_to)
            
        # Optimize query for the reports table
        return qs.select_related('client', 'loan', 'branch').order_by('-received_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticatedStaff(), IsBranchStaff()]
        if self.action == 'destroy':
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment, allocations = PaymentService.process_payment(
                serializer.validated_data, request.user
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        self.log_audit(
            action='CREATE',
            entity_type='Payment',
            entity_id=payment.id,
            new_values=PaymentSerializer(payment).data,
            obj=payment,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


# ============================================================
# Payment Allocation ViewSet (read-only)
# ============================================================
class PaymentAllocationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentAllocationSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['payment', 'installment']

    def get_queryset(self):
        return scope_queryset_by_branch(
            PaymentAllocation.objects.all(),
            self.request.user,
            branch_field='payment__branch',
        )


# ============================================================
# Branch Wallet ViewSet
# ============================================================
class BranchWalletViewSet(viewsets.ModelViewSet):
    serializer_class = BranchWalletSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['branch']

    def get_queryset(self):
        qs = scope_queryset_by_branch(BranchWallet.objects.all(), self.request.user)
        return qs.select_related('branch').order_by('branch__code')

    @action(detail=False, methods=['get'])
    def my_wallet(self, request):
        """Get the current user's branch wallet."""
        user = request.user
        if user.branch_id is None:
            return Response({'error': 'User is not assigned to a branch.'}, status=400)

        wallet, _ = BranchWallet.objects.get_or_create(branch=user.branch)
        return Response(BranchWalletSerializer(wallet).data)

    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Transfer funds between branches."""
        from_branch_id = request.data.get('from_branch')
        to_branch_id = request.data.get('to_branch')
        amount_raw = request.data.get('amount')
        channel = request.data.get('channel', 'CASH').upper()
        reference = request.data.get('reference', '').strip()

        if not all([from_branch_id, to_branch_id, amount_raw]):
            return Response({'error': 'Source, Destination, and Amount are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if from_branch_id == to_branch_id:
            return Response({'error': 'Cannot transfer to the same branch.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0: raise ValueError
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from_branch = Branch.objects.get(id=from_branch_id, organization=request.user.organization)
            to_branch = Branch.objects.get(id=to_branch_id, organization=request.user.organization)
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found.'}, status=status.HTTP_404_NOT_FOUND)

        txn_ref = reference or f'TRF-{timezone.now().strftime("%Y%m%d%H%M%S")}'

        try:
            with transaction.atomic():
                # 1. Deduct from source
                WalletService.record_movement(
                    branch=from_branch,
                    channel=channel,
                    amount=amount,
                    direction='OUT',
                    reference=txn_ref,
                    txn_type='TRANSFER_OUT',
                    user=request.user,
                    notes=f'Transfer to {to_branch.code}'
                )
                
                # 2. Add to destination
                WalletService.record_movement(
                    branch=to_branch,
                    channel=channel,
                    amount=amount,
                    direction='IN',
                    reference=txn_ref,
                    txn_type='TRANSFER_IN',
                    user=request.user,
                    notes=f'Transfer from {from_branch.code}'
                )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'Transfer successful.', 'reference': txn_ref})


# ============================================================
# Wallet Transaction ViewSet (read-only)
# ============================================================
class WalletTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'source_wallet', 'branch']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        qs = scope_queryset_by_branch(WalletTransaction.objects.all(), self.request.user)
        return qs.select_related('branch').order_by('-created_at')