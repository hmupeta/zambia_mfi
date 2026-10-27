# apps/payroll/serializers.py
from rest_framework import serializers
from .models import (
    StaffProfile, CommissionRule, PayrollRun, Payslip, 
    PayrollPeriod, PayrollSetting
)

class StaffProfileSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='user.get_full_name', read_only=True)
    role = serializers.CharField(source='user.get_role_display', read_only=True)

    class Meta:
        model = StaffProfile
        fields = '__all__'
        read_only_fields = ['id']


class CommissionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRule
        fields = '__all__'
        read_only_fields = ['id']


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = '__all__'
        read_only_fields = ['id']


class PayrollSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollSetting
        fields = '__all__'
        read_only_fields = ['id']


class PayslipSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    role = serializers.CharField(source='staff.get_role_display', read_only=True)

    class Meta:
        model = Payslip
        fields = '__all__'
        read_only_fields = ['id']


class PayrollRunSerializer(serializers.ModelSerializer):
    payslips = PayslipSerializer(many=True, read_only=True)
    # Nest the period details so the frontend gets the dates without a second API call
    period_details = PayrollPeriodSerializer(source='period', read_only=True)
    total_net_pay = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = '__all__'
        read_only_fields = ['id', 'status', 'processed_by', 'created_at']

    def get_total_net_pay(self, obj):
        return sum(p.net_pay for p in obj.payslips.all())