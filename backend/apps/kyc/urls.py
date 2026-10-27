from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    KYCDocumentRequirementViewSet,
    KYCVerificationViewSet, KYCDocumentViewSet, KYCCheckViewSet,
    KYCRiskAssessmentViewSet, KYCReviewScheduleViewSet, KYCSelfServiceViewSet,
)

router = DefaultRouter()
router.register(r'requirements', KYCDocumentRequirementViewSet, basename='kyc-requirement')
router.register(r'verifications', KYCVerificationViewSet, basename='kyc-verification')
router.register(r'documents', KYCDocumentViewSet, basename='kyc-document')
router.register(r'checks', KYCCheckViewSet, basename='kyc-check')
router.register(r'risk-assessments', KYCRiskAssessmentViewSet, basename='kyc-risk')
router.register(r'review-schedule', KYCReviewScheduleViewSet, basename='kyc-review-schedule')
router.register(r'self-service', KYCSelfServiceViewSet, basename='kyc-self-service')

urlpatterns = [path('', include(router.urls))]