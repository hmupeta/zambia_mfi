from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin, AuditLogMixin

from .models import ExpenseCategory, Expense
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    ExpenseCreateSerializer,
    ExpenseActionSerializer,
)
from .services import ExpenseService


# ============================================================
# Expense Categories
# ============================================================
class ExpenseCategoryViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.none()
    serializer_class = ExpenseCategorySerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'ExpenseCategory'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'requires_approval', 'gl_account']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# Expenses
# ============================================================
class ExpenseViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.none()
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'Expense'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'category', 'branch', 'payment_method']
    search_fields = ['expense_number', 'payee', 'description', 'reference']
    ordering_fields = ['expense_date', 'amount', 'created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related(
            'category', 'category__gl_account', 'branch', 'journal_entry',
        ).prefetch_related('approval_log__user')

    # ---------------- Workflow actions ----------------

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        expense = self.get_object()
        serializer = ExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ExpenseService.submit(expense, request.user, serializer.validated_data.get('comments', ''))
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExpenseSerializer(expense).data)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def approve(self, request, pk=None):
        expense = self.get_object()
        serializer = ExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ExpenseService.approve(expense, request.user, serializer.validated_data.get('comments', ''))
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExpenseSerializer(expense).data)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reject(self, request, pk=None):
        expense = self.get_object()
        serializer = ExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ExpenseService.reject(expense, request.user, serializer.validated_data.get('comments', ''))
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExpenseSerializer(expense).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        expense = self.get_object()
        serializer = ExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ExpenseService.mark_paid(
                expense,
                request.user,
                payment_method=serializer.validated_data.get('payment_method'),
                reference=serializer.validated_data.get('reference', ''),
                comments=serializer.validated_data.get('comments', ''),
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Expense marked as paid and posted to GL.',
            'expense': ExpenseSerializer(expense).data,
        })