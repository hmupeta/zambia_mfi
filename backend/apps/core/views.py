from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Organization, Branch, User, AuditLog
from .serializers import (
    OrganizationSerializer,
    BranchSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AuditLogSerializer,
)
from .permissions import (
    IsAuthenticatedStaff,
    IsObjectInBranch,
    IsHQAdmin,
    IsHQOrBranchManager,
    IsPlatformAdmin,
)
from .mixins import AuditLogMixin, OrganizationScopedMixin
from .rbac import scope_queryset_by_branch, is_hq
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework import generics, permissions
from .serializers import UserProfileSerializer


# ============================================================
# Organization ViewSet — platform admin only
# ============================================================
class OrganizationViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsPlatformAdmin]
    audit_entity_type = 'Organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'subscription_tier']
    search_fields = ['code', 'name', 'email']
    ordering_fields = ['name', 'created_at']


# ============================================================
# Branch ViewSet
# ============================================================
class BranchViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.none()
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'Branch'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_hq', 'is_active']
    search_fields = ['code', 'name', 'physical_address']
    ordering_fields = ['code', 'name', 'created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Branch.objects.none()

        user = self.request.user
        if not user or not user.is_authenticated:
            return Branch.objects.none()

        from .rbac import is_platform_admin, get_user_org_id
        qs = Branch.objects.all()

        # Platform admin with no org sees everything
        if is_platform_admin(user) and not get_user_org_id(user):
            return qs

        org_id = get_user_org_id(user)
        if org_id is None:
            return qs.none()

        qs = qs.filter(organization_id=org_id)

        # HQ admin sees all branches in the org
        if user.is_superuser or getattr(user, 'role', None) == 'HQ_ADMIN':
            return qs

        if getattr(user, 'branch_id', None) is None:
            return qs.none()

        return qs.filter(id=user.branch_id)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    def get_create_kwargs(self):
        user = self.request.user
        org = getattr(user, 'organization', None)
        if org is not None and not self.request.data.get('organization'):
            return {'organization': org}
        return {}


# ============================================================
# User ViewSet
# ============================================================
class UserViewSet(OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet):
    queryset = User.objects.none()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'User'
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'branch']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['username', 'date_joined', 'role']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedStaff(), IsHQOrBranchManager()]
        return super().get_permissions()

    def get_create_kwargs(self):
        """
        Non-HQ users can only create users in their own branch.
        org is auto-set via OrganizationScopedMixin.
        """
        kwargs = super().get_create_kwargs()
        user = self.request.user
        if not is_hq(user) and getattr(user, 'branch', None):
            kwargs['branch'] = user.branch
        return kwargs


# ============================================================
# AuditLog ViewSet (read-only)
# ============================================================
class AuditLogViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.none()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['action', 'entity_type', 'user', 'branch']
    search_fields = ['user__username', 'entity_type', 'action']
    ordering_fields = ['created_at']




# ============================================================
# Current user (profile) — read + update
# ============================================================
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    """
    GET  /api/auth/me/         → return current user's profile
    PATCH /api/auth/me/        → update name / email / phone
    """
    user = request.user

    if request.method == 'GET':
        return Response(UserSerializer(user).data)

    # Only allow updating a safe subset of fields
    ALLOWED = {'first_name', 'last_name', 'email', 'phone'}
    data = {k: v for k, v in request.data.items() if k in ALLOWED}

    if not data:
        return Response(
            {'error': 'No updatable fields provided.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = UserSerializer(user, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(UserSerializer(user).data)


#Exposes the user's fields along with their related organization and branch codes

class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ============================================================
# Change password
# ============================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    POST /api/auth/change-password/
    Body: { "old_password": "...", "new_password": "..." }
    """
    user = request.user
    old_password = request.data.get('old_password', '')
    new_password = request.data.get('new_password', '')

    if not old_password or not new_password:
        return Response(
            {'error': 'Both old and new passwords are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not user.check_password(old_password):
        return Response(
            {'error': 'Current password is incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if old_password == new_password:
        return Response(
            {'error': 'New password must be different from current password.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response(
            {'error': ' '.join(e.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save()

    return Response({
        'message': (
            'Password changed successfully. '
            'Please sign in again with your new password.'
        ),
    })