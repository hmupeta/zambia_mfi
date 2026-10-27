# apps/core/views_admin.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model

from .permissions import IsAuthenticatedStaff, IsHQAdmin
from .models import Branch, Organization
from .serializers_admin import (
    BranchAdminSerializer,
    UserAdminListSerializer,
    UserAdminDetailSerializer,
    SetPasswordSerializer,
)

User = get_user_model()


class BranchAdminViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.none()
    serializer_class = BranchAdminSerializer
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_hq']
    search_fields = ['code', 'name', 'physical_address']
    ordering_fields = ['code', 'name', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return Branch.objects.none()
        return (
            Branch.objects
            .filter(organization=org)
            .select_related('organization', 'parent_branch')
            .order_by('code')
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    #Enhanced branch details view support
        @action(detail=True, methods=['get'])
        def stats(self, request, pk=None):
            """Aggregated KPIs, staff, and recent activity for a branch."""
            from django.contrib.auth import get_user_model
            from django.db.models import Sum
            from apps.loans.models import Loan
            from apps.accounting.models import JournalEntry

            branch = self.get_object()
            User = get_user_model()

            # ── Loan portfolio KPIs ─────────────────────────────
            loans_qs = Loan.objects.filter(branch=branch)
            active_qs = loans_qs.filter(is_fully_repaid=False)

            portfolio = active_qs.aggregate(s=Sum('balance_due'))['s'] or 0
            active_count = active_qs.count()
            disbursed_total = loans_qs.aggregate(s=Sum('disbursed_amount'))['s'] or 0
            total_count = loans_qs.count()

            # ── Wallet balance (defensive — try common field names) ─
            wallet_balance = None
            try:
                from apps.payments.models import BranchWallet
                wallet = BranchWallet.objects.filter(branch=branch).first()
                if wallet:
                    for field in ('balance', 'current_balance', 'available_balance',
                                'wallet_balance', 'amount'):
                        if hasattr(wallet, field):
                            val = getattr(wallet, field)
                            if val is not None:
                                wallet_balance = float(val)
                                break
            except Exception:
                pass

            # ── Staff list ──────────────────────────────────────
            staff_qs = (
                User.objects
                .filter(branch=branch, is_active=True)
                .values('id', 'username', 'first_name', 'last_name', 'email', 'role')
                .order_by('first_name', 'last_name', 'username')
            )
            staff = []
            for u in staff_qs:
                full = f"{u['first_name'] or ''} {u['last_name'] or ''}".strip() or u['username']
                staff.append({
                    'id': u['id'],
                    'username': u['username'],
                    'full_name': full,
                    'email': u['email'] or '',
                    'role': u['role'] or '',
                    'role_display': (u['role'] or '').replace('_', ' ').title(),
                })

            # ── Recent journal entries ──────────────────────────
            recent_qs = (
                JournalEntry.objects
                .filter(branch=branch)
                .order_by('-entry_date', '-created_at')[:10]
                .values('id', 'entry_date', 'reference', 'description',
                        'source_type', 'is_posted', 'is_reversed')
            )
            recent = [
                {
                    'id': str(j['id']),
                    'entry_date': str(j['entry_date']),
                    'reference': j['reference'],
                    'description': (j['description'] or '')[:100],
                    'source_type': j['source_type'] or '—',
                    'is_posted': j['is_posted'],
                    'is_reversed': j['is_reversed'],
                }
                for j in recent_qs
            ]

            return Response({
                'kpis': {
                    'portfolio': float(portfolio),
                    'active_loans': active_count,
                    'total_loans': total_count,
                    'disbursed_total': float(disbursed_total),
                    'wallet_balance': wallet_balance,
                },
                'staff': staff,
                'recent_journal_entries': recent,
            })


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.none()
    # Default for safe methods (GET/HEAD/OPTIONS). Write actions are
    # gated below in get_permissions() to require HQ_ADMIN.
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_staff', 'role', 'branch']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['username', 'date_joined', 'last_login']

    def get_permissions(self):
        # Anyone on staff can LIST/RETRIEVE users — needed for officer
        # and assignee dropdowns throughout the app. Only HQ_ADMIN can
        # create/update/delete users or reset passwords.
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'set_password'):
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return [IsAuthenticatedStaff()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update', 'retrieve']:
            return UserAdminDetailSerializer
        return UserAdminListSerializer

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return User.objects.none()
        return (
            User.objects
            .filter(organization=org)
            .select_related('organization', 'branch')
            .order_by('username')
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    #stats
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Activity and workload stats for a user."""
        from apps.accounting.models import JournalEntry
        from apps.expenses.models import Expense
        from apps.loans.models import Loan
        from django.db.models import Sum, Count

        user = self.get_object()

        # ── Loans handled (defensive — try common creator field names) ─
        loans_handled = 0
        loans_value = 0.0
        try:
            loan_qs = None
            for field in ('created_by', 'loan_officer', 'officer', 'processed_by'):
                if hasattr(Loan, field):
                    loan_qs = Loan.objects.filter(**{field: user})
                    break
            if loan_qs is not None:
                loans_handled = loan_qs.count()
                loans_value = float(loan_qs.aggregate(s=Sum('amount'))['s'] or 0)
        except Exception:
            pass

        # ── Expenses requested ─
        expenses_count = 0
        expenses_value = 0.0
        try:
            exp_qs = None
            for field in ('created_by', 'requested_by', 'submitted_by'):
                if hasattr(Expense, field):
                    exp_qs = Expense.objects.filter(**{field: user})
                    break
            if exp_qs is not None:
                expenses_count = exp_qs.count()
                expenses_value = float(exp_qs.aggregate(s=Sum('amount'))['s'] or 0)
        except Exception:
            pass

        # ── Journal entries created ─
        je_count = 0
        try:
            if hasattr(JournalEntry, 'created_by'):
                je_count = JournalEntry.objects.filter(created_by=user).count()
        except Exception:
            pass

        # ── Recent journal entries ─
        recent_entries = []
        try:
            if hasattr(JournalEntry, 'created_by'):
                qs = (
                    JournalEntry.objects
                    .filter(created_by=user)
                    .order_by('-entry_date', '-created_at')[:10]
                    .values('id', 'entry_date', 'reference', 'description',
                            'source_type', 'is_posted', 'is_reversed')
                )
                recent_entries = [
                    {
                        'id': str(j['id']),
                        'entry_date': str(j['entry_date']),
                        'reference': j['reference'],
                        'description': (j['description'] or '')[:100],
                        'source_type': j['source_type'] or '—',
                        'is_posted': j['is_posted'],
                        'is_reversed': j['is_reversed'],
                    }
                    for j in qs
                ]
        except Exception:
            pass

        return Response({
            'kpis': {
                'loans_handled': loans_handled,
                'loans_value': loans_value,
                'expenses_count': expenses_count,
                'expenses_value': expenses_value,
                'journal_entries': je_count,
            },
            'recent_journal_entries': recent_entries,
        })

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: never actually delete a user; deactivate instead."""
        instance = self.get_object()
        if instance.pk == request.user.pk:
            return Response(
                {'error': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def set_password(self, request, pk=None):
        user = self.get_object()
        s = SetPasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user.set_password(s.validated_data['new_password'])
        user.save(update_fields=['password'])
        return Response({'message': f"Password updated for {user.username}."})

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {'error': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        return Response(UserAdminListSerializer(user).data)