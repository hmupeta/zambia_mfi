from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin, AuditLogMixin
from apps.loans.models import Loan

from .models import LoanRestructure
from .serializers import (
    LoanRestructureSerializer,
    LoanRestructureCreateSerializer,
    RestructureActionSerializer,
)
from .services import RestructureService


class LoanRestructureViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = LoanRestructure.objects.none()
    serializer_class = LoanRestructureSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'LoanRestructure'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'restructure_type', 'reason', 'loan', 'branch']
    search_fields = ['loan__loan_number', 'loan__client__first_name',
                     'loan__client__last_name', 'reason_notes']
    ordering_fields = ['created_at', 'applied_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related(
            'loan', 'loan__client', 'branch', 'proposed_by',
            'approved_by', 'journal_entry',
        ).prefetch_related('events__user')

    def create(self, request, *args, **kwargs):
        serializer = LoanRestructureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            loan = Loan.objects.get(pk=data.pop('loan'))
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            restructure = RestructureService.propose(loan, data, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        self.log_audit(
            action='CREATE', entity_type='LoanRestructure',
            entity_id=restructure.id,
            new_values=LoanRestructureSerializer(restructure).data,
            obj=restructure,
        )
        return Response(
            LoanRestructureSerializer(restructure).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def approve(self, request, pk=None):
        restructure = self.get_object()
        serializer = RestructureActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RestructureService.approve(
                restructure, request.user,
                serializer.validated_data.get('comments', ''),
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LoanRestructureSerializer(restructure).data)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reject(self, request, pk=None):
        restructure = self.get_object()
        serializer = RestructureActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RestructureService.reject(
                restructure, request.user,
                serializer.validated_data.get('reason', ''),
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LoanRestructureSerializer(restructure).data)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQAdmin])
    def apply(self, request, pk=None):
        restructure = self.get_object()
        serializer = RestructureActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RestructureService.apply(
                restructure, request.user,
                serializer.validated_data.get('comments', ''),
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': 'Restructure applied. New schedule generated.',
            'restructure': LoanRestructureSerializer(restructure).data,
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        restructure = self.get_object()
        serializer = RestructureActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RestructureService.cancel(
                restructure, request.user,
                serializer.validated_data.get('comments', ''),
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LoanRestructureSerializer(restructure).data)