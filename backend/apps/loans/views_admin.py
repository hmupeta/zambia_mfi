# apps/loans/views_admin.py
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Max
from django.shortcuts import render
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.restructures.models import LoanRestructure

from .models import Loan, PromiseToPay, LoanInstallment
from .serializers_admin import (
    LoanListSerializer, 
    LoanDetailSerializer, 
    PromiseToPaySerializer
)


class LoanAdminViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Loan.objects.none()
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'branch', 'loan_product', 'loan_officer', 'client']
    search_fields = ['loan_number', 'client__first_name', 'client__last_name', 'client__nrc']
    ordering_fields = ['created_at', 'loan_number', 'maturity_date', 'balance_due', 'amount']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LoanDetailSerializer
        return LoanListSerializer

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return Loan.objects.none()

        qs = (
            Loan.objects
            .filter(organization=org)
            .select_related('client', 'branch', 'loan_product', 'loan_officer')
            .prefetch_related('installments')
            .order_by('-created_at')
        )

        # 1. Filter by Overdue (Arrears)
        overdue = self.request.query_params.get('overdue')
        if overdue == 'true':
            today = date.today()
            qs = qs.filter(
                installments__due_date__lt=today,
                installments__is_paid=False,
            ).distinct()

        # 2. Filter by Date Range (for Reports Hub)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            qs = qs.filter(start_date__gte=date_from)
        if date_to:
            qs = qs.filter(start_date__lte=date_to)

        return qs

    # ------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def stats(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'total': 0, 'active': 0, 'in_arrears': 0, 'portfolio': 0})

        base = Loan.objects.filter(organization=org)

        total = base.count()
        active = base.filter(is_fully_repaid=False).count()
        portfolio = base.filter(is_fully_repaid=False).aggregate(
            s=Sum('balance_due'))['s'] or 0

        today = date.today()
        in_arrears = base.filter(
            installments__due_date__lt=today,
            installments__is_paid=False,
            is_fully_repaid=False,
        ).distinct().count()

        return Response({
            'total': total,
            'active': active,
            'in_arrears': in_arrears,
            'portfolio': float(portfolio),
        })

    # ------------------------------------------------------------
    # Collections Dashboard API
    # ------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def collections(self, request):
        """Returns overdue loans for the collections dashboard."""
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response([])
            
        today = timezone.now().date()

        # Find loans with unpaid installments past their due date
        overdue_loans = Loan.objects.filter(
            organization=org,
            is_fully_repaid=False,
            installments__is_paid=False,
            installments__due_date__lt=today
        ).distinct().select_related('client', 'branch', 'loan_officer', 'loan_product')

        data = []
        for loan in overdue_loans:
            # Find the oldest unpaid installment to calculate Days Past Due (DPD)
            oldest_inst = loan.installments.filter(is_paid=False).order_by('due_date').first()
            if oldest_inst:
                dpd = (today - oldest_inst.due_date).days
                # Sum the remaining amount for all unpaid installments
                overdue_amount = sum(
                    (i.total_due or 0) - (i.paid_amount or 0) 
                    for i in loan.installments.filter(is_paid=False)
                )
                
                # Fetch the latest active PENDING promise for this loan
                active_promise = loan.promises.filter(status='PENDING').order_by('promised_date').first()
                promise_data = None
                if active_promise:
                    promise_data = {
                        'amount': float(active_promise.amount),
                        'date': str(active_promise.promised_date),
                    }
                
                data.append({
                    'id': str(loan.id),
                    'loan_number': loan.loan_number,
                    'client_name': f"{loan.client.first_name} {loan.client.last_name}",
                    'client_phone': loan.client.phone,
                    'branch_code': loan.branch.code,
                    'officer_name': loan.loan_officer.get_full_name() if loan.loan_officer else 'Unassigned',
                    'dpd': dpd,
                    'overdue_amount': float(overdue_amount),
                    'balance_due': float(loan.balance_due),
                    'active_promise': promise_data,
                })

        # Sort by DPD descending (highest risk first)
        data.sort(key=lambda x: x['dpd'], reverse=True)
        return Response(data)

    # ------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------
    @action(detail=True, methods=['get'])
    def schedule(self, request, pk=None):
        loan = self.get_object()
        today = date.today()
        data = [
            {
                'installment_no': i.installment_no,
                'due_date': str(i.due_date),
                'principal': float(i.principal_amount or 0),
                'interest': float(i.interest_amount or 0),
                'penalty': float(i.penalty_amount or 0),
                'total_due': float(i.total_due or 0),
                'paid': float(i.paid_amount or 0),
                'remaining': float((i.total_due or 0) - (i.paid_amount or 0)),
                'status': (
                    'PAID' if i.is_paid
                    else ('OVERDUE' if i.due_date and i.due_date < today else 'PENDING')
                ),
                'is_paid': i.is_paid,
                'paid_at': i.paid_at.isoformat() if i.paid_at else None,
            }
            for i in loan.installments.all().order_by('installment_no')
        ]
        return Response({'loan_number': loan.loan_number, 'installments': data})

    # ------------------------------------------------------------
    # Disburse
    # ------------------------------------------------------------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def disburse(self, request, pk=None):
        """
        Transition APPROVED -> DISBURSED.
        Posts a JE: DR Loans Receivable / CR Cash|Bank|MoMo
        Updates BranchWallet.
        """
        from apps.accounting.models import GLAccount
        from apps.accounting.services import AccountingService

        loan = self.get_object()

        if loan.status not in ('APPROVED', 'PENDING'):
            return Response(
                {'error': f'Cannot disburse loan in status {loan.status}. '
                          f'Loan must be APPROVED first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- Inputs ----
        channel = (request.data.get('channel') or 'BANK').upper()
        reference = (request.data.get('reference') or '').strip()
        amount_raw = request.data.get('amount') or loan.amount
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0 or amount > float(loan.amount):
            return Response(
                {'error': f'Amount must be between 0 and {loan.amount}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        disbursement_date_raw = request.data.get('date')
        if disbursement_date_raw:
            try:
                disbursement_date = date.fromisoformat(disbursement_date_raw)
            except ValueError:
                return Response(
                    {'error': 'Invalid date format (use YYYY-MM-DD).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            disbursement_date = date.today()

        # ---- Resolve credit account (source of funds) ----
        credit_code = {
            'CASH':         '1010',
            'BANK':         '1020',
            'MTN_MOMO':     '1030',
            'AIRTEL_MONEY': '1030',
        }.get(channel, '1020')

        credit_account = GLAccount.objects.filter(
            organization=loan.organization,
            code=credit_code,
            is_active=True,
        ).first()

        if not credit_account:
            return Response(
                {'error': f'No GL account with code {credit_code} for channel '
                          f'{channel}. Configure the chart of accounts first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- Resolve debit account (Loans Receivable) ----
        debit_account = (
            GLAccount.objects.filter(
                organization=loan.organization, code__startswith='11', is_active=True,
            ).first()
            or GLAccount.objects.filter(
                organization=loan.organization,
                name__icontains='loan receivable',
                is_active=True,
            ).first()
            or GLAccount.objects.filter(
                organization=loan.organization,
                name__icontains='loans receivable',
                is_active=True,
            ).first()
        )

        if not debit_account:
            return Response(
                {'error': 'No Loans Receivable GL account found. Create one '
                          '(e.g., code 1100 "Loans Receivable").'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- Post the journal entry ----
        try:
            je = AccountingService.create_journal_entry(
                organization=loan.organization,
                entry_date=disbursement_date,
                reference=loan.loan_number,
                description=f'Loan disbursement: {loan.loan_number}',
                lines=[
                    {
                        'account_code': debit_account.code,
                        'debit': amount,
                        'memo': f'Loan {loan.loan_number} disbursed',
                    },
                    {
                        'account_code': credit_account.code,
                        'credit': amount,
                        'memo': f'Disbursed via {channel}' + (f' - {reference}' if reference else ''),
                    },
                ],
                source_type='Loan',
                source_id=loan.id,
                branch=loan.branch,
                user=request.user,
            )
        except Exception as e:
            return Response(
                {'error': f'GL posting failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ---- Update loan ----
        loan.status = 'DISBURSED'
        loan.disbursed_amount = amount
        loan.start_date = disbursement_date
        loan.disbursement_channel = channel
        loan.disbursement_ref = reference
        loan.disbursement_journal_entry = je
        loan.save(update_fields=[
            'status', 'disbursed_amount', 'start_date',
            'disbursement_channel', 'disbursement_ref',
            'disbursement_journal_entry', 'updated_at',
        ])

        # ---- Update branch wallet ----
        try:
            from apps.payments.services_wallet import WalletService
            WalletService.record_movement(
                branch=loan.branch,
                channel=channel,
                amount=amount,
                direction='OUT',
                reference=loan.loan_number,
                txn_type='DISBURSEMENT',
                user=request.user,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Wallet update failed: {e}")

        # -- Send disbursement notification --
        try:
            from apps.notifications.triggers import on_loan_disbursed
            on_loan_disbursed(loan, user=request.user)
        except Exception:
            pass

        return Response(LoanDetailSerializer(loan).data)

    # ------------------------------------------------------------
    # Restructure
    # ------------------------------------------------------------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def restructure(self, request, pk=None):
        loan = self.get_object()
        reason_notes = (request.data.get('reason') or '').strip()
        new_term_months = int(request.data.get('new_term_months') or 0)

        if not reason_notes or new_term_months <= 0:
            return Response(
                {'error': 'A reason and a valid term length in months are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if loan.status in ('CLOSED', 'WRITTEN_OFF'):
            return Response(
                {'error': f'Cannot restructure a loan in status {loan.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Archive current state
        old_balance = loan.balance_due
        old_maturity = loan.maturity_date
        old_count = loan.installments.count()
        new_principal = loan.balance_due
        
        # 2. Calculate new schedule
        product = loan.loan_product
        rate = Decimal(str(product.interest_rate or 0)) / Decimal('100')
        total_interest = new_principal * rate * (Decimal(new_term_months) / Decimal('12'))
        total_due = new_principal + total_interest
        
        per_inst_principal = new_principal / Decimal(new_term_months)
        per_inst_interest = total_interest / Decimal(new_term_months)
        new_maturity = timezone.now().date() + timedelta(days=30 * new_term_months)

        # 3. Create the Restructure Record
        LoanRestructure.objects.create(
            loan=loan,
            restructure_type='EXTEND_TERM',
            reason='OTHER', # Required choice field
            reason_notes=reason_notes,
            original_principal=loan.amount,
            original_balance=old_balance,
            original_installment_count=old_count,
            original_maturity_date=old_maturity,
            new_start_date=timezone.now().date(),
            new_maturity_date=new_maturity,
            new_installment_count=new_term_months,
            new_installment_amount=per_inst_principal + per_inst_interest,
            new_interest_rate=product.interest_rate,
            new_repayment_frequency=loan.repayment_frequency,
            status='APPLIED',
            proposed_by=request.user,
            proposed_at=timezone.now(),
            approved_by=request.user, # Auto-approve for this flow
            approved_at=timezone.now(),
            applied_at=timezone.now()
        )

        # 4. Delete old unpaid installments
        loan.installments.filter(is_paid=False).delete()

        # 5. Find max installment no (so we don't clash with paid ones)
        max_inst = loan.installments.aggregate(m=Max('installment_no'))['m'] or 0

        # 6. Update Loan
        loan.balance_due = total_due
        loan.maturity_date = new_maturity
        loan.status = 'ACTIVE' 
        loan.save(update_fields=['balance_due', 'maturity_date', 'status', 'updated_at'])

        # 7. Generate new schedule
        for i in range(1, new_term_months + 1):
            due = timezone.now().date() + timedelta(days=30 * i)
            LoanInstallment.objects.create(
                loan=loan,
                installment_no=max_inst + i,
                due_date=due,
                principal_amount=per_inst_principal,
                interest_amount=per_inst_interest,
                total_due=per_inst_principal + per_inst_interest,
                status='PENDING'
            )

        return Response(LoanDetailSerializer(loan).data)

    # ------------------------------------------------------------
    # Write-off
    # ------------------------------------------------------------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticatedStaff, IsHQAdmin])
    def write_off(self, request, pk=None):
        loan = self.get_object()

        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'error': 'Reason is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if loan.status == 'WRITTEN_OFF':
            return Response(
                {'error': 'Loan is already written off.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        loan.status = 'WRITTEN_OFF'
        loan.closed_at = timezone.now()
        loan.save(update_fields=['status', 'closed_at', 'updated_at'])

        return Response(LoanDetailSerializer(loan).data)


class PromiseToPayViewSet(viewsets.ModelViewSet):
    queryset = PromiseToPay.objects.none()
    serializer_class = PromiseToPaySerializer
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['loan', 'status']

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return PromiseToPay.objects.none()
        return PromiseToPay.objects.filter(loan__organization=org).select_related('loan', 'logged_by')

    def perform_create(self, serializer):
        serializer.save(logged_by=self.request.user)


# ============================================================
# Page shells (server-rendered)
# ============================================================
def loan_products_list(request):
    return render(request, 'app/loans/loan_products_list.html', {
        'page_title': 'Loan Products',
    })


def loan_product_new(request):
    return render(request, 'app/loans/loan_product_form.html', {
        'page_title': 'New Loan Product',
        'mode': 'create',
        'product_id': '',
    })


def loan_product_detail(request, pk):
    return render(request, 'app/loans/loan_product_detail.html', {
        'page_title': 'Loan Product',
        'product_id': str(pk),
    })


def loan_product_edit(request, pk):
    return render(request, 'app/loans/loan_product_form.html', {
        'page_title': 'Edit Loan Product',
        'mode': 'edit',
        'product_id': str(pk),
    })

def collections_dashboard(request):
    return render(request, 'app/loans/collections.html')