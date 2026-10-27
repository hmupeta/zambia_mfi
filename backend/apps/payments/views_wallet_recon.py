# apps/payments/views_wallet_recon.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin
from apps.core.models import Branch

from .models import WalletReconciliation
from .serializers_wallet import (
    WalletReconciliationSerializer,
    ReconcileRequestSerializer,
    ResolveReconciliationSerializer,
)
from .services_wallet import WalletService


class WalletReconciliationViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = WalletReconciliation.objects.none()
    serializer_class = WalletReconciliationSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['branch', 'status']
    ordering_fields = ['reconciled_at', 'variance_total']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related(
            'branch', 'reconciled_by', 'resolved_by',
        ).order_by('-reconciled_at')

    @action(detail=False, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reconcile(self, request):
        """POST /api/payments/wallet-reconciliations/reconcile/"""
        s = ReconcileRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            branch = Branch.objects.get(
                id=d['branch'], organization=request.user.organization,
            )
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found.'}, status=404)

        recon = WalletService.reconcile(
            branch=branch,
            physical_cash=d['physical_cash'],
            physical_momo=d['physical_momo'],
            physical_bank=d['physical_bank'],
            notes=d.get('notes', ''),
            user=request.user,
        )
        return Response(
            WalletReconciliationSerializer(recon).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQAdmin])
    def resolve(self, request, pk=None):
        recon = self.get_object()
        s = ResolveReconciliationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            recon = WalletService.resolve(
                recon, request.user, s.validated_data['resolution_notes'],
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        return Response(WalletReconciliationSerializer(recon).data)