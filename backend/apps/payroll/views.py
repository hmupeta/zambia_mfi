# apps/payroll/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.core.permissions import IsHRPayroll
from .models import StaffProfile, CommissionRule, PayrollRun, Payslip
from .serializers import (
    StaffProfileSerializer, CommissionRuleSerializer, 
    PayrollRunSerializer, PayslipSerializer
)
from .services import PayrollService

class StaffProfileViewSet(viewsets.ModelViewSet):
    serializer_class = StaffProfileSerializer
    permission_classes = [IsAuthenticated, IsHRPayroll]

    def get_queryset(self):
        return StaffProfile.objects.filter(user__organization=self.request.user.organization)

class CommissionRuleViewSet(viewsets.ModelViewSet):
    serializer_class = CommissionRuleSerializer
    permission_classes = [IsAuthenticated, IsHRPayroll]

    def get_queryset(self):
        return CommissionRule.objects.filter(organization=self.request.user.organization)

class PayrollRunViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated, IsHRPayroll]

    def get_queryset(self):
        return PayrollRun.objects.filter(organization=self.request.user.organization).prefetch_related('payslips')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            processed_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Triggers the PayrollService to calculate salaries and commissions.
        """
        payroll_run = self.get_object()
        
        if payroll_run.status == 'COMPLETED':
            return Response({'error': 'This payroll run has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            PayrollService.generate_payslips(payroll_run)
            return Response({'message': 'Payroll calculated successfully.', 'status': 'COMPLETED'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated, IsHRPayroll]

    def get_queryset(self):
        return Payslip.objects.filter(
            payroll_run__organization=self.request.user.organization
        ).select_related('staff', 'payroll_run')