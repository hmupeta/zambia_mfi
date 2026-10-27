# apps/payments/views_wallet_stats.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum

from apps.core.permissions import IsAuthenticatedStaff
from .models import BranchWallet


@api_view(['GET'])
@permission_classes([IsAuthenticatedStaff])
def wallet_stats(request):
    """
    GET /api/payments/wallets/stats/

    Returns aggregate balances across all branches (org-scoped).
    HQ admins see all branches; branch users see only their branch.
    """
    user = request.user
    org = getattr(user, 'organization', None)
    if not org:
        return Response({
            'total_branches': 0, 'cash': 0, 'momo': 0, 'bank': 0, 'total': 0,
        })

    qs = BranchWallet.objects.filter(branch__organization=org)

    role = getattr(user, 'role', '') or ''
    is_hq_admin = (role == 'HQ_ADMIN') or getattr(user, 'is_superuser', False)
    if not is_hq_admin:
        if getattr(user, 'branch', None):
            qs = qs.filter(branch=user.branch)

    agg = qs.aggregate(
        cash=Sum('cash_balance'),
        momo=Sum('mobile_money_balance'),
        bank=Sum('bank_balance'),
    )
    cash = float(agg['cash'] or 0)
    momo = float(agg['momo'] or 0)
    bank = float(agg['bank'] or 0)

    return Response({
        'total_branches': qs.count(),
        'cash': cash,
        'momo': momo,
        'bank': bank,
        'total': cash + momo + bank,
    })