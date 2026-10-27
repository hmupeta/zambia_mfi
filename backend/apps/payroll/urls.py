# apps/payroll/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StaffProfileViewSet, CommissionRuleViewSet, PayrollRunViewSet, PayslipViewSet

router = DefaultRouter()
router.register(r'profiles', StaffProfileViewSet, basename='staff-profile')
router.register(r'rules', CommissionRuleViewSet, basename='commission-rule')
router.register(r'runs', PayrollRunViewSet, basename='payroll-run')
router.register(r'payslips', PayslipViewSet, basename='payslip')

urlpatterns = [
    path('', include(router.urls)),
]