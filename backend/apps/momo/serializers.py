# apps/momo/serializers.py
from rest_framework import serializers

from .models import MomoProviderConfig, PaymentIntent, DisbursementIntent


# ═══════════════════════════════════════════════════════════
# Provider Config — read/write, secrets are write-only
# ═══════════════════════════════════════════════════════════
class MomoProviderConfigSerializer(serializers.ModelSerializer):
    provider_display = serializers.CharField(
        source='get_provider_code_display', read_only=True,
    )
    branch_name = serializers.CharField(
        source='branch.name', read_only=True, allow_null=True,
    )
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display', read_only=True,
    )

    class Meta:
        model = MomoProviderConfig
        fields = [
            'id',
            'organization',
            'branch',
            'branch_name',
            'provider_code',
            'provider_display',
            'transaction_type',             # <--- ADDED
            'transaction_type_display',     # <--- ADDED
            'display_name',
            'is_active',
            'is_sandbox',
            'merchant_id',
            'short_code',
            'collection_gl_code',
            'disbursement_gl_code',
            'callback_url',
            'webhook_secret',
            'subscription_key',
            'api_key',
            'api_secret',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'organization', 'created_at', 'updated_at',
            'provider_display', 'branch_name', 'transaction_type_display',
        ]
        extra_kwargs = {
            'organization':      {'required': False},
            'subscription_key':  {'write_only': True, 'required': False},
            'api_key':           {'write_only': True, 'required': False},
            'api_secret':        {'write_only': True, 'required': False},
            'webhook_secret':    {'write_only': True, 'required': False},
        }

    def validate(self, attrs):
        """
        Enforce uniqueness based on (org, branch, provider_code, transaction_type).
        This allows one Collection and one Disbursement config per branch.
        """
        request = self.context.get('request')
        org = attrs.get('organization') or (request.user.organization if request else None)
        branch = attrs.get('branch', getattr(self.instance, 'branch', None))
        provider_code = attrs.get(
            'provider_code',
            getattr(self.instance, 'provider_code', None),
        )
        transaction_type = attrs.get(
            'transaction_type',
            getattr(self.instance, 'transaction_type', 'COLLECTION'),
        )

        # Check if a config with the EXACT same parameters already exists
        qs = MomoProviderConfig.objects.filter(
            organization=org,
            provider_code=provider_code,
            branch=branch,
            transaction_type=transaction_type, # <--- ADDED TO QUERY
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            where = f'branch {branch.code}' if branch else 'all branches (MFI-wide)'
            raise serializers.ValidationError(
                f'A {provider_code} ({transaction_type}) config already exists for {where}. '
                'Edit the existing one instead.'
            )
        return attrs

    def update(self, instance, validated_data):
        for field in ('api_key', 'api_secret',
                      'subscription_key', 'webhook_secret'):
            if not validated_data.get(field):
                validated_data.pop(field, None)
        return super().update(instance, validated_data)


# ═══════════════════════════════════════════════════════════
# PaymentIntent
# ═══════════════════════════════════════════════════════════
class PaymentIntentSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)
    payment_number = serializers.CharField(source='payment.payment_number', read_only=True)

    class Meta:
        model = PaymentIntent
        fields = '__all__'

    def get_client_name(self, obj):
        if not obj.client:
            return ''
        return f'{obj.client.first_name} {obj.client.last_name}'.strip()


# ═══════════════════════════════════════════════════════════
# DisbursementIntent
# ═══════════════════════════════════════════════════════════
class DisbursementIntentSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    loan_number = serializers.CharField(source='loan.loan_number', read_only=True)

    class Meta:
        model = DisbursementIntent
        fields = '__all__'

    def get_client_name(self, obj):
        if not obj.client:
            return ''
        return f'{obj.client.first_name} {obj.client.last_name}'.strip()