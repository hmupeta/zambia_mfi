from rest_framework import serializers
from .models import Branch, User, AuditLog
from rest_framework import serializers
from .models import Organization, Branch, User, AuditLog
from rest_framework import serializers
from django.contrib.auth import get_user_model


# ============================================================
# Organization
# ============================================================
class OrganizationSerializer(serializers.ModelSerializer):
    branch_count = serializers.IntegerField(source='branches.count', read_only=True)
    user_count = serializers.IntegerField(source='users.count', read_only=True)

    class Meta:
        model = Organization
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'branch_count', 'user_count']


# ============================================================
# Branch
# ============================================================
class BranchSerializer(serializers.ModelSerializer):
    parent_branch_name = serializers.CharField(
        source='parent_branch.name', read_only=True
    )

    class Meta:
        model = Branch
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


# ============================================================
# User (read)
# ============================================================
class UserSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    organization_code = serializers.CharField(source='organization.code', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'phone',
            'first_name', 'last_name',
            'role', 'branch', 'branch_name', 'branch_code',
            'organization', 'organization_name', 'organization_code',
            'is_platform_admin', 'is_active', 'date_joined',
        ]
        read_only_fields = ['id', 'date_joined']


# ============================================================
# User (create)
# ============================================================
class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'phone',
            'first_name', 'last_name',
            'role', 'branch', 'password',
            'is_active',
        ]

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

# Exposes the user's fields along with their related organization and branch codes.

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    # Assuming your User model has foreign keys to Organization and Branch
    organization_code = serializers.CharField(source='organization.code', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    role = serializers.SerializerMethodField()
    initial = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'phone',
            'role', 'organization_code', 'branch_code', 
            'date_joined', 'initial', 'name'
        ]
        read_only_fields = ['id', 'username', 'role', 'organization_code', 'branch_code', 'date_joined']

    def get_role(self, obj):
        # Adjust this based on how you store roles (e.g., groups or a role field)
        if obj.is_superuser:
            return "HQ ADMIN"
        return obj.groups.first().name if obj.groups.exists() else "User"

    def get_initial(self, obj):
        return obj.first_name[0].upper() if obj.first_name else obj.username[0].upper()

    def get_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


# ============================================================
# User (update)
# ============================================================
class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8
    )

    class Meta:
        model = User
        fields = [
            'email', 'phone',
            'first_name', 'last_name',
            'role', 'branch', 'is_active',
            'password',
        ]

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


# ============================================================
# Audit Log (read-only)
# ============================================================
class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = [
            'id', 'user', 'branch', 'action', 'entity_type',
            'entity_id', 'old_values', 'new_values',
            'ip_address', 'created_at',
        ]   # <-- explicit list, not the `fields` string