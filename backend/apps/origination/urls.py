from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WorkflowTemplateViewSet,
    LoanApplicationViewSet,
    ApplicationDocumentViewSet,
    ApplicationTransitionViewSet,
    ApplicationReviewViewSet,
    TaskViewSet,
    CustomerLoanViewSet,
    CustomerApplyLoanView, # <-- Added
)
# Import the Product ViewSet from the loans app
from apps.loans.views import LoanProductViewSet # <-- Added

router = DefaultRouter()
router.register(r'workflows', WorkflowTemplateViewSet, basename='workflow-template')
router.register(r'applications', LoanApplicationViewSet, basename='loan-application')
router.register(r'documents', ApplicationDocumentViewSet, basename='application-document')
router.register(r'transitions', ApplicationTransitionViewSet, basename='application-transition')
router.register(r'reviews', ApplicationReviewViewSet, basename='application-review')
router.register(r'tasks', TaskViewSet, basename='task')

# Customer App Routes
router.register(r'customer/loans', CustomerLoanViewSet, basename='customer-loans')
router.register(r'customer/products', LoanProductViewSet, basename='customer-products') # <-- Added

urlpatterns = [
    # Custom path for applying for a loan
    path('customer/apply/', CustomerApplyLoanView.as_view(), name='customer-apply'), # <-- Added
    path('', include(router.urls)),
]