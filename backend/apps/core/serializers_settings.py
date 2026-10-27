# apps/core/serializers_settings.py
import re
from rest_framework import serializers
from .models import OrganizationSettings, FeatureFlag


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    
    # These are read-only outputs for the frontend to display the current images
    logo_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    
    # Explicitly declare the file fields so DRF handles the multipart form data correctly
    logo = serializers.ImageField(required=False, allow_null=True)
    favicon = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = OrganizationSettings
        # 'exclude' automatically includes all other fields (legal_name, colors, SMS keys, etc.)
        exclude = ['id', 'organization', 'updated_at']
        read_only_fields = ['updated_at']

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url

    def get_favicon_url(self, obj):
        if not obj.favicon:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.favicon.url) if request else obj.favicon.url

    def validate_accent_color(self, v):
        return self._validate_hex(v, 'accent_color')

    def validate_primary_color(self, v):
        return self._validate_hex(v, 'primary_color')

    def validate_fiscal_year_start_month(self, v):
        if not (1 <= v <= 12):
            raise serializers.ValidationError('Must be between 1 and 12.')
        return v

    def validate_password_min_length(self, v):
        if v < 6:
            raise serializers.ValidationError('Minimum password length must be at least 6.')
        return v

    @staticmethod
    def _validate_hex(v, field):
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v or ''):
            raise serializers.ValidationError(f'{field} must be a hex color like #B45309.')
        return v


class FeatureFlagSerializer(serializers.ModelSerializer):
    branch_codes = serializers.SerializerMethodField()

    class Meta:
        model = FeatureFlag
        fields = [
            'id', 'key', 'name', 'description', 'enabled',
            'enabled_for_branches', 'branch_codes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_branch_codes(self, obj):
        return list(obj.enabled_for_branches.values_list('code', flat=True))