# apps/core/serializers_admin.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Branch, Organization

User = get_user_model()


# ============================================================
# Branch
# ============================================================
class BranchAdminSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    parent_branch_code = serializers.CharField(source='parent_branch.code', read_only=True, default=None)
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = [
            'id', 'code', 'name',
            'organization', 'organization_name',
            'parent_branch', 'parent_branch_code',
            'physical_address', 'phone',
            'latitude', 'longitude',
            'is_hq', 'is_active',
            'user_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']

    def get_user_count(self, obj):
        try:
            return obj.users.count()
        except Exception:
            return 0


# ============================================================
# User
# ============================================================
class UserAdminListSerializer(serializers.ModelSerializer):
    """Compact representation for table rows."""
    full_name = serializers.SerializerMethodField()
    branch_code = serializers.CharField(source='branch.code', read_only=True, default=None)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    organization_code = serializers.CharField(source='organization.code', read_only=True, default=None)
    role_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_display',
            'organization', 'organization_code',
            'branch', 'branch_code', 'branch_name',
            'is_active', 'is_staff', 'is_superuser', 'is_platform_admin',
            'last_login', 'date_joined',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined']

    def get_full_name(self, obj):
        name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return name or obj.username

    def get_role_display(self, obj):
        if not obj.role:
            return None
        return obj.role.replace('_', ' ').title()


class UserAdminDetailSerializer(UserAdminListSerializer):
    """Full representation for the edit form."""
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8,
        help_text='Leave blank to keep the current password.',
    )

    class Meta(UserAdminListSerializer.Meta):
        fields = UserAdminListSerializer.Meta.fields + ['password']

    def validate_username(self, value):
        qs = User.objects.filter(username=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A user with this username already exists.')
        return value

    def validate_email(self, value):
        if not value:
            return value
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(required=True, min_length=8)