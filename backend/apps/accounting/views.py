from datetime import date
from decimal import Decimal

from django.db.models import Sum

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from apps.core.permissions import (
    IsAuthenticatedStaff,
    IsHQAdmin,
    IsHQOrBranchManager,
)
from apps.core.mixins import OrganizationScopedMixin

from .models import GLAccount, JournalEntry, LoanLossProvision
from .serializers import (
    GLAccountSerializer,
    JournalEntrySerializer,
    JournalEntryCreateSerializer,
    LoanLossProvisionSerializer,
)
from .schemas import (
    TrialBalanceResponseSerializer,
    IncomeStatementResponseSerializer,
    BalanceSheetResponseSerializer,
    NPLReturnResponseSerializer,
    PortfolioAtRiskResponseSerializer,
)
from .services import AccountingService
from .reports import BoZReportGenerator
from .services_provisioning import ProvisioningService


# ============================================================
# Chart of Accounts
# ============================================================
class GLAccountViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = GLAccount.objects.none()
    serializer_class = GLAccountSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['account_type', 'is_active', 'is_contra']
    search_fields = ['code', 'name']
    ordering_fields = ['code', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def with_balances(self, request):
        """
        Return every GL account with its current balance.
        Query params:
            as_of (optional): YYYY-MM-DD — balance as of that date
        """
        qs = self.get_queryset()
        as_of = request.query_params.get('as_of')

        accounts = []
        for account in qs.order_by('code'):
            lines = account.journal_lines.filter(
                journal_entry__is_posted=True,
                journal_entry__is_reversed=False,
            )
            if as_of:
                lines = lines.filter(journal_entry__entry_date__lte=as_of)

            agg = lines.aggregate(dr=Sum('debit'), cr=Sum('credit'))
            dr = agg['dr'] or Decimal('0')
            cr = agg['cr'] or Decimal('0')

            if account.is_debit_normal:
                balance = dr - cr
            else:
                balance = cr - dr

            accounts.append({
                'id': str(account.id),
                'code': account.code,
                'name': account.name,
                'account_type': account.account_type,
                'is_contra': account.is_contra,
                'is_active': account.is_active,
                'balance': float(balance),
                'total_debit': float(dr),
                'total_credit': float(cr),
            })

        return Response({'accounts': accounts})


# ============================================================
# Journal Entries
# ============================================================
class JournalEntryViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = JournalEntry.objects.none()
    serializer_class = JournalEntrySerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['source_type', 'is_posted', 'is_reversed', 'branch']
    search_fields = ['reference', 'description']
    ordering_fields = ['entry_date', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    @action(detail=False, methods=['post'])
    def manual(self, request):
        """Create a manual journal entry."""
        serializer = JournalEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            je = AccountingService.create_journal_entry(
                organization=request.user.organization,
                entry_date=data['entry_date'],
                reference=data['reference'],
                description=data['description'],
                lines=data['lines'],
                source_type='Manual',
                user=request.user,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # Catch-all so we always return a clean JSON error, never crash the worker
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'{type(e).__name__}: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            JournalEntrySerializer(je).data,
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# Loan Loss Provisions
# ============================================================
class LoanLossProvisionViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LoanLossProvision.objects.none()
    serializer_class = LoanLossProvisionSerializer
    org_field = 'loan__organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['classification', 'provision_date', 'loan']
    ordering_fields = ['provision_date', 'provision_amount']

    @action(detail=False, methods=['post'])
    def run(self, request):
        """Trigger provisioning for the caller's organization."""
        if request.user.role != 'HQ_ADMIN' and not request.user.is_superuser:
            return Response(
                {'error': 'HQ admin required.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        as_of = request.data.get('as_of_date') or date.today()
        summary = ProvisioningService.run_for_organization(
            request.user.organization, as_of_date=as_of,
        )
        return Response(summary)


# ============================================================
# Financial Statements
# ============================================================
@extend_schema(
    tags=['Accounting - Financial Statements'],
    summary='Trial Balance',
    description='Lists every GL account with total debits and credits as of a date.',
    responses={200: TrialBalanceResponseSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def trial_balance(request):
    as_of = request.query_params.get('as_of') or date.today()
    org = request.user.organization
    data = AccountingService.trial_balance(org, as_of)
    return Response({'as_of': as_of, 'rows': data})


@extend_schema(
    tags=['Accounting - Financial Statements'],
    summary='Income Statement (P&L)',
    description='Revenue − Expenses = Net Income for a period.',
    responses={200: IncomeStatementResponseSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def income_statement(request):
    from_date = request.query_params.get('from') or date.today().replace(day=1)
    to_date = request.query_params.get('to') or date.today()
    org = request.user.organization
    return Response(AccountingService.income_statement(org, from_date, to_date))


@extend_schema(
    tags=['Accounting - Financial Statements'],
    summary='Balance Sheet',
    description='Assets = Liabilities + Equity + (Income − Expenses) as of a date.',
    responses={200: BalanceSheetResponseSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def balance_sheet(request):
    as_of_param = request.query_params.get('as_of')
    as_of = date.fromisoformat(as_of_param) if as_of_param else date.today()
    org = request.user.organization

    data = AccountingService.balance_sheet(org, as_of)

    # ----------------------------------------------------------
    # FIX: Add current-year net income to equity so that
    # Assets = Liabilities + Equity + (Income - Expenses)
    # ----------------------------------------------------------
    fiscal_year_start = as_of.replace(month=1, day=1)

    def _to_decimal(v):
        if v is None:
            return Decimal('0')
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal('0')

    try:
        pnl = AccountingService.income_statement(org, fiscal_year_start, as_of)

        def _sum_any(raw):
            """Accept either a scalar number OR a list of row dicts."""
            if raw is None:
                return Decimal('0')
            # Case 1: scalar number
            if isinstance(raw, (int, float, Decimal, str)):
                return _to_decimal(raw)
            # Case 2: list of rows -> sum their 'amount'/'balance'
            if isinstance(raw, list):
                total = Decimal('0')
                for r in raw:
                    if isinstance(r, dict):
                        amt = r.get('amount')
                        if amt is None:
                            amt = r.get('balance')
                        total += _to_decimal(amt)
                return total
            # Case 3: dict with a 'total' key
            if isinstance(raw, dict):
                return _to_decimal(raw.get('total') or raw.get('amount'))
            return Decimal('0')

        revenue_raw = pnl.get('revenue', pnl.get('income', pnl.get('revenues')))
        expenses_raw = pnl.get('expenses', pnl.get('expense'))

        total_income = _sum_any(revenue_raw)
        total_expense = _sum_any(expenses_raw)

        # Prefer the service's own net_income if present
        if pnl.get('net_income') is not None:
            net_income = _to_decimal(pnl.get('net_income'))
        else:
            net_income = total_income - total_expense

        # Final safety net: if we still got 0 but the sheet is out of balance,
        # use the difference so the badge reflects reality.
        if net_income == Decimal('0'):
            assets_tmp = _to_decimal(data.get('total_assets'))
            liab_tmp = _to_decimal(data.get('total_liabilities'))
            equity_tmp = _to_decimal(data.get('total_equity'))
            net_income = assets_tmp - liab_tmp - equity_tmp
    except Exception:
        net_income = Decimal('0')

    # Append net income as a synthetic equity line
    equity_list = list(data.get('equity') or [])
    equity_list.append({
        'code': '',
        'name': 'Current Year Net Income',
        'amount': float(net_income),
    })
    data['equity'] = equity_list

    # Recompute total equity
    total_equity = Decimal('0')
    for e in equity_list:
        total_equity += _to_decimal(e.get('amount') or 0)
    data['total_equity'] = float(total_equity)

    # Recompute the balanced flag
    total_assets = _to_decimal(data.get('total_assets'))
    total_liabilities = _to_decimal(data.get('total_liabilities'))
    diff = total_assets - (total_liabilities + total_equity)
    data['balanced'] = abs(diff) < Decimal('0.01')
    data['difference'] = float(diff)
    # ----------------------------------------------------------

    return Response(data)


# ============================================================
# Bank of Zambia Reports
# ============================================================
@extend_schema(
    tags=['Accounting - BoZ Reports'],
    summary='NPL Return (BoZ)',
    description='Bank of Zambia Non-Performing Loan schedule.',
    responses={200: NPLReturnResponseSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQAdmin])
def npl_return(request):
    as_of = request.query_params.get('as_of')
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    return Response(
        BoZReportGenerator.npl_return(request.user.organization, as_of_date)
    )


@extend_schema(
    tags=['Accounting - BoZ Reports'],
    summary='Portfolio at Risk (PAR)',
    description='PAR 1 / 7 / 30 / 60 / 90 as percentages of the portfolio.',
    responses={200: PortfolioAtRiskResponseSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff, IsHQOrBranchManager])
def portfolio_at_risk(request):
    as_of = request.query_params.get('as_of')
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    return Response(
        BoZReportGenerator.portfolio_at_risk(request.user.organization, as_of_date)
    )