# apps/loans/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    LoanProductViewSet,
    BranchLoanProductViewSet,
    LoanGroupViewSet,
    LoanGroupMemberViewSet,
    LoanInstallmentViewSet,
    LoanViewSet,
)
from .views_admin import LoanAdminViewSet, PromiseToPayViewSet
from .views_groups import (
    LoanGroupViewSet as GroupViewSet,
    GroupMeetingViewSet,
    GroupCollectionViewSet,
)

router = DefaultRouter()
router.register(r'products', LoanProductViewSet, basename='loan-product')
router.register(r'branch-products', BranchLoanProductViewSet, basename='branch-loan-product')
router.register(r'groups', GroupViewSet, basename='loan-group')
router.register(r'group-meetings', GroupMeetingViewSet, basename='group-meeting')
router.register(r'group-collections', GroupCollectionViewSet, basename='group-collection')
router.register(r'group-members', LoanGroupMemberViewSet, basename='loan-group-member')
router.register(r'installments', LoanInstallmentViewSet, basename='loan-installment')
router.register(r'admin', LoanAdminViewSet, basename='loan-admin')

# Register specific routes BEFORE the catch-all r'' route
router.register(r'promises', PromiseToPayViewSet, basename='promise-to-pay')

# Catch-all route MUST be last
router.register(r'', LoanViewSet, basename='loan')

urlpatterns = [
    path('', include(router.urls)),
]