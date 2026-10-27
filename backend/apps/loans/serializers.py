from rest_framework import serializers
from .models import (
    LoanProduct, BranchLoanProduct, LoanGroup, LoanGroupMember,
    Loan, LoanInstallment, LoanProductFee,
)
from datetime import datetime, timedelta


# ============================================================
# Loan Product
# ============================================================
class LoanProductFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanProductFee
        fields = [
            'id', 'fee_type', 'name', 'calculation_method',
            'amount', 'percentage', 'charge_timing', 'is_active',
        ]
        read_only_fields = ['id']


class LoanProductSerializer(serializers.ModelSerializer):
    fees = LoanProductFeeSerializer(many=True, required=False)

    # Display helpers so the UI doesn't have to translate enum codes
    category_display = serializers.CharField(
        source='get_category_display', read_only=True,
    )
    interest_method_display = serializers.CharField(
        source='get_interest_method_display', read_only=True,
    )
    repayment_frequency_display = serializers.CharField(
        source='get_repayment_frequency_display', read_only=True,
    )
    interest_rate_period_display = serializers.CharField(
        source='get_interest_rate_period_display', read_only=True,
    )

    class Meta:
        model = LoanProduct
        fields = [
            'id', 'code', 'name', 'description',
            'category', 'category_display',
            'min_amount', 'max_amount',
            'min_tenure_months', 'max_tenure_months',
            'interest_method', 'interest_method_display',
            'interest_rate', 'interest_rate_period',
            'interest_rate_period_display',
            'effective_interest_rate',
            'penalty_rate', 'grace_days', 'first_installment_grace_days',
            'repayment_frequency', 'repayment_frequency_display',
            'requires_guarantor', 'requires_collateral', 'allow_group_loan',
            'is_active', 'created_at',
            'fees',
        ]
        read_only_fields = ['id', 'created_at', 'effective_interest_rate']

    def validate(self, data):
        # Basic cross-field validation for the form
        min_a = data.get('min_amount', getattr(self.instance, 'min_amount', None))
        max_a = data.get('max_amount', getattr(self.instance, 'max_amount', None))
        if min_a is not None and max_a is not None and min_a > max_a:
            raise serializers.ValidationError({
                'max_amount': 'Max amount must be greater than or equal to min amount.',
            })

        min_t = data.get('min_tenure_months', getattr(self.instance, 'min_tenure_months', None))
        max_t = data.get('max_tenure_months', getattr(self.instance, 'max_tenure_months', None))
        if min_t is not None and max_t is not None and min_t > max_t:
            raise serializers.ValidationError({
                'max_tenure_months': 'Max tenure must be greater than or equal to min tenure.',
            })

        return data

    def create(self, validated_data):
        fees_data = validated_data.pop('fees', [])
        product = super().create(validated_data)
        for fee in fees_data:
            LoanProductFee.objects.create(loan_product=product, **fee)
        return product

    def update(self, instance, validated_data):
        fees_data = validated_data.pop('fees', None)
        instance = super().update(instance, validated_data)
        # Replace the whole fee set — simplest contract for the UI
        if fees_data is not None:
            instance.fees.all().delete()
            for fee in fees_data:
                LoanProductFee.objects.create(loan_product=instance, **fee)
        return instance


# ============================================================
# Branch Loan Product
# ============================================================
class BranchLoanProductSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    product_name = serializers.CharField(source='loan_product.name', read_only=True)

    class Meta:
        model = BranchLoanProduct
        fields = '__all__'


# ============================================================
# Loan Group
# ============================================================
class LoanGroupSerializer(serializers.ModelSerializer):
    leader_name = serializers.CharField(source='leader.full_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = LoanGroup
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class LoanGroupMemberSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)

    class Meta:
        model = LoanGroupMember
        fields = '__all__'


# ============================================================
# Loan / Installments
# ============================================================
class LoanInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanInstallment
        fields = '__all__'
        read_only_fields = ['id']


class LoanSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    product_name = serializers.CharField(source='loan_product.name', read_only=True)
    installments = LoanInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = Loan
        fields = '__all__'
        read_only_fields = ['id', 'loan_number', 'created_at', 'updated_at']


class LoanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = ['client', 'loan_product', 'amount', 'start_date', 'loan_officer', 'loan_group']

    def validate(self, data):
        # Check branch matches
        client = data['client']
        product = data['loan_product']

        if (client.branch != self.context['request'].user.branch
                and self.context['request'].user.role != 'HQ_ADMIN'):
            raise serializers.ValidationError(
                'Cannot create loan for client in different branch'
            )

        # Check amount within product limits
        if data['amount'] < product.min_amount or data['amount'] > product.max_amount:
            raise serializers.ValidationError(
                f'Amount must be between {product.min_amount} and {product.max_amount}'
            )

        return data

    def create(self, validated_data):
        import uuid
        loan_number = (
            f"LN-{datetime.now().strftime('%Y%m%d')}-"
            f"{str(uuid.uuid4())[:8].upper()}"
        )
        validated_data['loan_number'] = loan_number

        product = validated_data['loan_product']
        start_date = validated_data['start_date']
        maturity_date = start_date + timedelta(days=product.max_tenure_months * 30)
        validated_data['maturity_date'] = maturity_date

        loan = Loan.objects.create(**validated_data)

        from .services import LoanService
        LoanService.generate_installments(loan)

        return loan