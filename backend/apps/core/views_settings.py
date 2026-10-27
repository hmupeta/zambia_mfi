# apps/core/views_settings.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend

from .permissions import IsAuthenticatedStaff, IsHQAdmin
from .models import OrganizationSettings, FeatureFlag
from .serializers_settings import (
    OrganizationSettingsSerializer,
    FeatureFlagSerializer,
)


class OrganizationSettingsViewSet(viewsets.ViewSet):
    """
    Singleton viewset — always operates on the current user's organization.
    GET   /api/core/settings/         → retrieve
    PATCH /api/core/settings/         → update (partial)
    POST  /api/core/settings/         → update (upsert; supports file uploads)
    """
    permission_classes = [IsAuthenticatedStaff, IsHQAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_settings(self, request):
        return OrganizationSettings.for_org(request.user.organization)

    def list(self, request):
        obj = self._get_settings(request)
        serializer = OrganizationSettingsSerializer(obj, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        return self.list(request)

    def create(self, request):
        # POST is treated as an update because the object is a singleton
        return self._update(request)

    def update(self, request, pk=None):
        return self._update(request)

    def partial_update(self, request, pk=None):
        return self._update(request)

    def _update(self, request):
        obj = self._get_settings(request)
        serializer = OrganizationSettingsSerializer(
            obj, data=request.data, partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class FeatureFlagViewSet(viewsets.ModelViewSet):
    queryset = FeatureFlag.objects.none()
    serializer_class = FeatureFlagSerializer
    permission_classes = [IsAuthenticatedStaff, IsHQAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['enabled']
    search_fields = ['key', 'name', 'description']
    ordering_fields = ['key', 'name', 'updated_at']

    def get_queryset(self):
        org = getattr(self.request.user, 'organization', None)
        if not org:
            return FeatureFlag.objects.none()
        return (
            FeatureFlag.objects
            .filter(organization=org)
            .prefetch_related('enabled_for_branches')
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)