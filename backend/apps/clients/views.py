from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Client, ClientPaymentChannel, Guarantor, ClientDocument
from .serializers import (
    ClientSerializer,
    ClientPaymentChannelSerializer,
    GuarantorSerializer,
    ClientDocumentSerializer,
)
from apps.core.permissions import (
    IsAuthenticatedStaff,
    IsObjectInBranch,
    IsHQAdmin,
    IsBranchStaff,
)
from apps.core.mixins import AuditLogMixin, OrganizationScopedMixin
from apps.core.rbac import scope_queryset_by_branch, is_hq


# ============================================================
# Client ViewSet
# ============================================================
class ClientViewSet(OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet):
    queryset = Client.objects.none()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'Client'
    org_field = 'organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['branch', 'kyc_status', 'is_active', 'gender', 'province']
    search_fields = ['first_name', 'last_name', 'nrc', 'phone', 'email', 'occupation']
    ordering_fields = ['created_at', 'first_name', 'last_name']

    def get_queryset(self):
        """
        Override: apply branch-level filtering in addition to org scoping.
        """
        qs = super().get_queryset()  # Already filtered by org
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()

        # HQ admins see all branches in the org
        if is_hq(user):
            return qs

        # Others see only their branch
        if getattr(user, 'branch_id', None) is None:
            return qs.none()

        return qs.filter(branch_id=user.branch_id)

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticatedStaff(), IsBranchStaff()]
        if self.action == 'destroy':
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    def get_create_kwargs(self):
        kwargs = super().get_create_kwargs()  # gives {organization: <org>} if applicable
        user = self.request.user
        kwargs['created_by'] = user
        if not is_hq(user) and getattr(user, 'branch', None):
            kwargs['branch'] = user.branch
        return kwargs


# ============================================================
# Client Payment Channel ViewSet
# ============================================================
class ClientPaymentChannelViewSet(
    OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet
):
    queryset = ClientPaymentChannel.objects.none()
    serializer_class = ClientPaymentChannelSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'ClientPaymentChannel'
    org_field = 'client__organization'  # nested lookup
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client', 'channel_type', 'is_default', 'is_verified']
    search_fields = ['account_number', 'account_name',
                     'client__first_name', 'client__last_name']


# ============================================================
# Guarantor ViewSet
# ============================================================
class GuarantorViewSet(OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet):
    queryset = Guarantor.objects.none()
    serializer_class = GuarantorSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'Guarantor'
    org_field = 'client__organization'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['client']
    search_fields = ['name', 'phone', 'nrc']


# ============================================================
# Client Document ViewSet
# ============================================================
class ClientDocumentViewSet(
    OrganizationScopedMixin, AuditLogMixin, viewsets.ModelViewSet
):
    queryset = ClientDocument.objects.none()
    serializer_class = ClientDocumentSerializer
    permission_classes = [IsAuthenticatedStaff, IsObjectInBranch]
    audit_entity_type = 'ClientDocument'
    org_field = 'client__organization'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['client', 'document_type']

    def get_create_kwargs(self):
        return {'uploaded_by': self.request.user}