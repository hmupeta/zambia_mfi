# apps/accounting/views_bank.py
from decimal import Decimal

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin, AuditLogMixin

from .models import (
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
    JournalLine,
)
from .serializers_bank import (
    BankAccountSerializer,
    BankStatementSerializer,
    BankStatementCreateSerializer,
    BankStatementLineSerializer,
    BankReconciliationSerializer,
    ManualMatchSerializer,
    UnmatchedGLLineSerializer,
)
from .services_bank import AutoMatchingService, ReconciliationService


# ============================================================
# Bank Accounts
# ============================================================
class BankAccountViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.none()
    serializer_class = BankAccountSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'BankAccount'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['branch', 'is_active', 'currency']
    search_fields = ['bank_name', 'account_number', 'account_name']
    ordering_fields = ['bank_name', 'account_number', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# Bank Statements
# ============================================================
class BankStatementViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = BankStatement.objects.none()
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff, IsHQOrBranchManager]
    audit_entity_type = 'BankStatement'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['bank_account', 'status', 'source']
    search_fields = ['notes']
    ordering_fields = ['period_to', 'created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return BankStatementCreateSerializer
        return BankStatementSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('bank_account').prefetch_related(
            'lines__matched_journal_line__journal_entry',
        )

    @action(detail=True, methods=['post'])
    def auto_match(self, request, pk=None):
        """Run auto-matching for this statement."""
        statement = self.get_object()
        result = AutoMatchingService.auto_match_statement(statement, user=request.user)
        return Response({
            'message': 'Auto-match complete.',
            'matched': result['matched'],
            'unmatched': result['unmatched'],
            'statement_status': statement.status,
        })

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Compute and persist a reconciliation snapshot."""
        statement = self.get_object()
        report = ReconciliationService.compute(statement)

        recon = BankReconciliation.objects.create(
            organization=statement.bank_account.organization,   # ✅ fixed source
            bank_account=statement.bank_account,
            statement=statement,
            as_of_date=statement.period_to,
            created_by=request.user,
            statement_opening_balance=report['statement_opening_balance'],
            statement_closing_balance=report['statement_closing_balance'],
            gl_opening_balance=report['gl_opening_balance'],
            gl_closing_balance=report['gl_closing_balance'],
            reconciled_difference=report['difference'],
            is_reconciled=report['is_reconciled'],
        )
        return Response({
            'reconciliation_id': str(recon.id),
            'report': report,
        })


# ============================================================
# Statement Lines
# ============================================================
class BankStatementLineViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = BankStatementLine.objects.none()
    serializer_class = BankStatementLineSerializer
    org_field = 'statement__organization'
    permission_classes = [IsAuthenticatedStaff, IsHQOrBranchManager]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['statement', 'match_status']
    ordering_fields = ['transaction_date', 'id']

    @action(detail=True, methods=['get'])
    def suggestions(self, request, pk=None):
        """
        Return ranked candidate journal lines for this bank line.
        Used by the Alpine.js UI to populate the auto-match panel.
        """
        bank_line = self.get_object()
        candidates = AutoMatchingService.suggest_matches(bank_line, limit=10)
        return Response({
            'bank_line_id': bank_line.id,
            'candidates': candidates,
        })

    @action(detail=True, methods=['post'])
    def manual_match(self, request, pk=None):
        """Manually match this line to a journal line."""
        statement_line = self.get_object()

        serializer = ManualMatchSerializer(data={
            'statement_line_id': statement_line.id,
            'journal_line_id': request.data.get('journal_line_id'),
        })
        serializer.is_valid(raise_exception=True)

        try:
            jl = JournalLine.objects.get(
                pk=serializer.validated_data['journal_line_id'],
                account=statement_line.statement.bank_account.gl_account,
            )
        except JournalLine.DoesNotExist:
            return Response(
                {'error': 'Journal line not found on the linked bank GL account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(jl, 'statement_match') and jl.statement_match is not None:
            return Response(
                {'error': 'That journal line is already matched to another statement line.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Score the pair so the audit trail records confidence
        score = AutoMatchingService.score_pair(statement_line, jl)

        statement_line.matched_journal_line = jl
        statement_line.match_status = 'MANUAL_MATCHED'
        statement_line.match_score = Decimal(str(score['total']))
        statement_line.match_rule = 'manual'
        statement_line.matched_at = timezone.now()
        statement_line.matched_by = request.user
        statement_line.save()

        # Update parent statement status
        statement = statement_line.statement
        if not statement.lines.filter(match_status='UNMATCHED').exists():
            statement.status = 'RECONCILED'
            statement.save(update_fields=['status'])

        return Response(BankStatementLineSerializer(statement_line).data)

    @action(detail=True, methods=['post'])
    def unmatch(self, request, pk=None):
        line = self.get_object()
        line.matched_journal_line = None
        line.match_status = 'UNMATCHED'
        line.match_score = None
        line.match_rule = ''
        line.matched_at = None
        line.matched_by = None
        line.save()

        # Revert statement status if any line is unmatched
        statement = line.statement
        statement.status = 'IN_PROGRESS'
        statement.save(update_fields=['status'])

        return Response(BankStatementLineSerializer(line).data)

    @action(detail=True, methods=['post'])
    def exclude(self, request, pk=None):
        """Exclude a line from reconciliation (e.g., informational entries)."""
        line = self.get_object()
        line.match_status = 'EXCLUDED'
        line.matched_journal_line = None
        line.save()
        return Response(BankStatementLineSerializer(line).data)


# ============================================================
# Reconciliations
# ============================================================
class BankReconciliationViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = BankReconciliation.objects.none()
    serializer_class = BankReconciliationSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff, IsHQOrBranchManager]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['bank_account', 'status', 'is_reconciled']
    ordering_fields = ['as_of_date', 'created_at']


# ============================================================
# Unmatched GL Lines (helper for manual matching)
# ============================================================
class UnmatchedGLLineViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists journal lines on a bank account's GL that have NOT yet been
    matched to a bank statement line. Used by the UI to populate the
    manual-match dropdown.
    """
    serializer_class = UnmatchedGLLineSerializer

    def get_queryset(self):
        from apps.core.rbac import get_user_org_id, is_platform_admin

        user = self.request.user
        if not user or not user.is_authenticated:
            return JournalLine.objects.none()

        qs = JournalLine.objects.filter(
            journal_entry__is_posted=True,
            journal_entry__is_reversed=False,
            statement_match__isnull=True,
            account__account_type='ASSET',
        ).select_related('account', 'journal_entry')

        gl_account_id = self.request.query_params.get('gl_account_id')
        if gl_account_id:
            qs = qs.filter(account_id=gl_account_id)

        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if date_from:
            qs = qs.filter(journal_entry__entry_date__gte=date_from)
        if date_to:
            qs = qs.filter(journal_entry__entry_date__lte=date_to)

        if is_platform_admin(user) and not get_user_org_id(user):
            return qs.order_by('-journal_entry__entry_date')[:200]

        org_id = get_user_org_id(user)
        if org_id is None:
            return qs.none()

        return qs.filter(
            account__organization_id=org_id,
        ).order_by('-journal_entry__entry_date')[:200]