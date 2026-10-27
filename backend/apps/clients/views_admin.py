# apps/clients/views_admin.py
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager

from .models import Client
from .serializers_admin import (
    ClientListSerializer,
    ClientDetailSerializer,
    ClientWriteSerializer,
)


class ClientAdminViewSet(viewsets.ModelViewSet):
    """
    Full CRUD + stats for clients.

    Endpoints:
        GET    /api/clients/admin/                  → list (paginated, filterable)
        POST   /api/clients/admin/                  → create
        GET    /api/clients/admin/stats/            → KPI counters
        GET    /api/clients/admin/{id}/             → detail
        PATCH  /api/clients/admin/{id}/             → partial update
        PUT    /api/clients/admin/{id}/             → full update
        DELETE /api/clients/admin/{id}/             → soft-delete
        GET    /api/clients/admin/{id}/loans/       → client's loans
        GET    /api/clients/admin/{id}/payments/    → client's payments
        POST   /api/clients/admin/{id}/verify_kyc/  → mark KYC verified
        POST   /api/clients/admin/{id}/deactivate/  → soft-disable
        POST   /api/clients/admin/{id}/reactivate/  → re-enable
    """
    queryset = Client.objects.none()
    permission_classes = [IsAuthenticatedStaff]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['kyc_status', 'is_active', 'branch', 'gender', 'province']
    search_fields = ['nrc', 'first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['created_at', 'first_name', 'last_name', 'nrc', 'credit_score']

    # ────────────────────────────────────────────────────
    # Serializer selection
    # ────────────────────────────────────────────────────
    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ClientWriteSerializer
        if self.action == 'retrieve':
            return ClientDetailSerializer
        return ClientListSerializer

    # ────────────────────────────────────────────────────
    # Permission overrides
    # ────────────────────────────────────────────────────
    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update'):
            return [IsAuthenticatedStaff(), IsHQOrBranchManager()]
        if self.action == 'destroy':
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    # ────────────────────────────────────────────────────
    # Queryset — org-scoped, soft-delete aware
    # (annotations removed; serializer computes counts/sums
    #  via SerializerMethodField for reliability)
    # ────────────────────────────────────────────────────
    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return Client.objects.none()

        return (
            Client.objects
            .filter(organization=org, deleted_at__isnull=True)
            .select_related('branch', 'created_by')
            .order_by('-created_at')
        )

    # ────────────────────────────────────────────────────
    # List-level actions
    # ────────────────────────────────────────────────────
    @action(detail=False, methods=['get'])
    def stats(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({
                'total': 0, 'verified': 0, 'pending': 0, 'active': 0,
            })

        base = Client.objects.filter(organization=org, deleted_at__isnull=True)

        return Response({
            'total':     base.count(),
            'verified':  base.filter(kyc_status='VERIFIED').count(),
            'pending':   base.filter(
                kyc_status__in=['PENDING', 'IN_REVIEW', 'SUBMITTED']
            ).count(),
            'active':    base.filter(is_active=True).count(),
        })

    # ────────────────────────────────────────────────────
    # Detail-level actions
    # ────────────────────────────────────────────────────
    @action(detail=True, methods=['get'])
    def loans(self, request, pk=None):
        """Return all loans for this client (list serializer)."""
        from apps.loans.serializers_admin import LoanListSerializer

        client = self.get_object()
        qs = (
            client.loans
            .select_related('branch', 'loan_product', 'loan_officer')
            .prefetch_related('installments')
            .order_by('-created_at')
        )
        return Response(
            LoanListSerializer(qs, many=True, context={'request': request}).data
        )

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        """Return the most recent 50 payments across all of the client's loans."""
        client = self.get_object()
        payments = (
            client.payments
            .select_related('loan')
            .order_by('-received_at')[:50]
        )

        rows = []
        for p in payments:
            rows.append({
                'id': str(p.id),
                'amount': float(p.amount or 0),
                'received_at': (
                    p.received_at.isoformat()
                    if getattr(p, 'received_at', None) else None
                ),
                'reference': getattr(p, 'reference', '') or '',
                'channel': (
                    getattr(p, 'channel', '')
                    or getattr(p, 'payment_method', '')
                    or ''
                ),
                'loan_id': str(p.loan_id) if getattr(p, 'loan_id', None) else None,
                'loan_number': (
                    getattr(p.loan, 'loan_number', '')
                    if getattr(p, 'loan', None) else ''
                ),
            })
        return Response(rows)

    @action(
        detail=True, methods=['post'],
        permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager],
    )
    def verify_kyc(self, request, pk=None):
        client = self.get_object()
        if client.kyc_status == 'VERIFIED':
            return Response(
                {'error': 'Client is already verified.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        client.kyc_status = 'VERIFIED'
        client.save(update_fields=['kyc_status', 'updated_at'])
        return Response(
            ClientDetailSerializer(client, context={'request': request}).data
        )

    @action(
        detail=True, methods=['post'],
        permission_classes=[IsAuthenticatedStaff, IsHQAdmin],
    )
    def deactivate(self, request, pk=None):
        client = self.get_object()
        if not client.is_active:
            return Response(
                {'error': 'Client is already inactive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        client.is_active = False
        client.save(update_fields=['is_active', 'updated_at'])
        return Response(
            ClientDetailSerializer(client, context={'request': request}).data
        )

    @action(
        detail=True, methods=['post'],
        permission_classes=[IsAuthenticatedStaff, IsHQAdmin],
    )
    def reactivate(self, request, pk=None):
        client = self.get_object()
        client.is_active = True
        client.save(update_fields=['is_active', 'updated_at'])
        return Response(
            ClientDetailSerializer(client, context={'request': request}).data
        )

    # ────────────────────────────────────────────────────
    # Soft-delete override
    # ────────────────────────────────────────────────────
    def destroy(self, request, *args, **kwargs):
        """Soft-delete: set deleted_at instead of hard delete."""
        client = self.get_object()

        # Block delete if client has active loans
        active_loans = client.loans.filter(is_fully_repaid=False).count()
        if active_loans > 0:
            return Response(
                {'error': f'Cannot delete client with {active_loans} active loan(s). '
                          f'Deactivate instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.utils import timezone
        client.deleted_at = timezone.now()
        client.is_active = False
        client.save(update_fields=['deleted_at', 'is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)