from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentViewSet,
    PaymentAllocationViewSet,
    BranchWalletViewSet,
    WalletTransactionViewSet,
)
from .views_admin import PaymentAdminViewSet
from .views_wallet_recon import WalletReconciliationViewSet
from .views_wallet_stats import wallet_stats
from .views_field import FieldCollectionViewSet 

router = DefaultRouter()
router.register(r'allocations', PaymentAllocationViewSet, basename='payment-allocation')
router.register(r'wallets', BranchWalletViewSet, basename='branch-wallet')
router.register(r'transactions', WalletTransactionViewSet, basename='wallet-transaction')
router.register(r'wallet-reconciliations', WalletReconciliationViewSet, basename='wallet-reconciliation')
router.register(r'admin', PaymentAdminViewSet, basename='payment-admin')
router.register(r'field-collections', FieldCollectionViewSet, basename='field-collection')

router.register(r'', PaymentViewSet, basename='payment')

urlpatterns = [
    # Register the standalone stats route BEFORE the router so it wins
    path('wallets/stats/', wallet_stats, name='wallet-stats'),
    path('', include(router.urls)),
]