from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    LoanProduct, BranchLoanProduct, LoanGroup,
    LoanGroupMember, Loan, LoanInstallment,
)
from .serializers import (
    LoanProductSerializer,
    BranchLoanProductSerializer,
    LoanGroupSerializer,
    LoanGroupMemberSerializer,
    LoanSerializer,
    LoanCreateSerializer,
    LoanInstallmentSerializer,
)
from apps.core.permissions import (
    IsAuthenticatedStaff,
    IsObjectInBranch,
    IsHQAdmin,
    IsHQOrBranchManager,
    IsBranchStaff,
)
from apps.core.mixins import AuditLogMixin, OrganizationScopedMixin
from apps.core.rbac import is_hq


# ============================================================
# Loan Product ViewSet
# ============================================================
class LoanProductViewSet(
    OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet
):
    queryset = LoanProduct.objects.none()
    serializer_class = LoanProductSerializer
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'LoanProduct'
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active', 'interest_method', 'repayment_frequency']
    search_fields = ['code', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# Branch Loan Product ViewSet
# ============================================================
class BranchLoanProductViewSet(
    OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet
):
    queryset = BranchLoanProduct.objects.none()
    serializer_class = BranchLoanProductSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'BranchLoanProduct'
    org_field = 'branch__organization'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['branch', 'loan_product', 'is_active']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# Loan Group ViewSet
# ============================================================
class LoanGroupViewSet(OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet):
    queryset = LoanGroup.objects.none()
    serializer_class = LoanGroupSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'LoanGroup'
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['branch']
    search_fields = ['group_name']

    def get_create_kwargs(self):
        kwargs = super().get_create_kwargs()
        user = self.request.user
        if not is_hq(user) and getattr(user, 'branch', None):
            kwargs['branch'] = user.branch
        return kwargs


# ============================================================
# Loan Group Member ViewSet
# ============================================================
class LoanGroupMemberViewSet(
    OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet
):
    queryset = LoanGroupMember.objects.none()
    serializer_class = LoanGroupMemberSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'LoanGroupMember'
    org_field = 'loan_group__organization'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['loan_group', 'client']


# ============================================================
# Loan ViewSet
# ============================================================
class LoanViewSet(OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet):
    queryset = Loan.objects.none()
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'Loan'
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'branch', 'client', 'loan_product']
    search_fields = ['loan_number', 'client__first_name', 'client__last_name', 'client__nrc']
    ordering_fields = ['created_at', 'amount', 'maturity_date']

    def get_serializer_class(self):
        if self.action == 'create':
            return LoanCreateSerializer
        return LoanSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'schedule']:
            return [IsAuthenticatedStaff(), IsBranchStaff()]
        if self.action in ['create', 'update', 'partial_update']:
            return [IsAuthenticatedStaff(), IsBranchStaff()]
        if self.action in ['approve', 'disburse']:
            return [IsAuthenticatedStaff(), IsHQOrBranchManager()]
        if self.action == 'destroy':
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        loan = self.get_object()
        if loan.status != 'PENDING':
            return Response(
                {'error': 'Loan is not in PENDING status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        loan.status = 'APPROVED'
        loan.approved_by = request.user
        loan.save()

        self.log_audit(
            action='UPDATE', entity_type='Loan', entity_id=loan.id,
            new_values=LoanSerializer(loan).data, obj=loan,
        )
        return Response({'message': 'Loan approved.', 'loan': LoanSerializer(loan).data})

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        loan = self.get_object()
        if loan.status != 'APPROVED':
            return Response(
                {'error': 'Loan is not in APPROVED status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = request.data.get('amount', loan.amount)
        channel = request.data.get('channel', 'CASH')
        reference = request.data.get('reference', '')

        loan.status = 'ACTIVE'
        loan.disbursed_amount = amount
        loan.disbursement_channel = channel
        loan.disbursement_ref = reference
        loan.save()

        self.log_audit(
            action='UPDATE', entity_type='Loan', entity_id=loan.id,
            new_values=LoanSerializer(loan).data, obj=loan,
        )
        return Response({'message': 'Loan disbursed.', 'loan': LoanSerializer(loan).data})

    @action(detail=True, methods=['get'])
    def schedule(self, request, pk=None):
        loan = self.get_object()
        installments = loan.installments.all()
        return Response(LoanInstallmentSerializer(installments, many=True).data)


# ============================================================
# Loan Installment ViewSet (read-only)
# ============================================================
class LoanInstallmentViewSet(
    OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet
):
    queryset = LoanInstallment.objects.none()
    serializer_class = LoanInstallmentSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    org_field = 'loan__organization'
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'loan']
    ordering_fields = ['due_date', 'installment_no']