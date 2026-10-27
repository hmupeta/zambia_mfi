from rest_framework import serializers
from .models import Payment, PaymentAllocation, BranchWallet, WalletTransaction
from .models import FieldCollection
from drf_spectacular.utils import extend_schema_serializer

class PaymentAllocationSerializer(serializers.ModelSerializer):
    installment_no = serializers.IntegerField(source='installment.installment_no', read_only=True)
    
    class Meta:
        model = PaymentAllocation
        fields = '__all__'
        read_only_fields = ['id', 'allocated_at']

class PaymentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    received_by_name = serializers.CharField(source='received_by.username', read_only=True)
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['id', 'payment_number', 'received_at']

@extend_schema_serializer(component_name="AdminPaymentCreateSerializer")
class PaymentCreateSerializer(serializers.Serializer):
    loan_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=['CASH', 'MTN_MOMO', 'AIRTEL_MONEY', 'BANK'])
    transaction_ref = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero")
        return value

class BranchWalletSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    
    class Meta:
        model = BranchWallet
        fields = '__all__'
        read_only_fields = ['id', 'updated_at']

class WalletTransactionSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class FieldCollectionSerializer(serializers.ModelSerializer):
    # These read-only fields make it easy for the frontend to display names
    recorded_by_name = serializers.CharField(source='recorded_by.username', read_only=True)
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = FieldCollection
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'branch', 'status', 'recorded_by', 'created_at', 'reviewed_by', 'reviewed_at']

    def get_client_name(self, obj):
        if not obj.loan or not obj.loan.client:
            return None
        return f"{obj.loan.client.first_name} {obj.loan.client.last_name}"