# apps/momo/serializers_admin.py

from rest_framework import serializers

from .models import MomoProviderConfig


class MomoProviderConfigSerializer(serializers.ModelSerializer):
    """
    Read/write serializer for MomoProviderConfig.

    Secrets (api_key, api_secret, subscription_key, webhook_secret) are
    accepted on write but NEVER returned on read. Update semantics:
    sending a blank value keeps the existing secret.
    """
    provider_display = serializers.CharField(
        source='get_provider_code_display', read_only=True,
    )

    class Meta:
        model = MomoProviderConfig
        fields = [
            'id',
            'provider_code',
            'provider_display',
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
        read_only_fields = ['id', 'created_at', 'updated_at', 'provider_display']
        extra_kwargs = {
            # write-only secrets, blank on update means "keep"
            'subscription_key': {'write_only': True, 'required': False},
            'api_key':          {'write_only': True, 'required': False},
            'api_secret':       {'write_only': True, 'required': False},
            'webhook_secret':   {'write_only': True, 'required': False},
        }

    def update(self, instance, validated_data):
        # Blank secret fields on PATCH mean "leave unchanged" — not "clear".
        for field in ('api_key', 'api_secret',
                      'subscription_key', 'webhook_secret'):
            if not validated_data.get(field):
                validated_data.pop(field, None)
        return super().update(instance, validated_data)