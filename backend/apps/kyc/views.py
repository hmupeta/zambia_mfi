from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin, IsHQOrBranchManager
from apps.core.mixins import OrganizationScopedMixin, AuditLogMixin
from apps.clients.models import Client

from .models import (
    KYCDocumentRequirement, KYCVerification, KYCDocument, KYCCheck,
    KYCRiskAssessment, KYCReviewSchedule, KYCSelfServiceToken,
)
from .serializers import (
    KYCDocumentRequirementSerializer,
    KYCVerificationSerializer, KYCInitiateSerializer,
    KYCRunChecksSerializer, KYCVerifySerializer, KYCRejectSerializer,
    KYCDocumentSerializer, KYCCheckSerializer, KYCRiskAssessmentSerializer,
    KYCReviewScheduleSerializer, SelfServiceTokenSerializer,
    SelfServiceSubmitSerializer,
)
from .services import (
    KYCVerificationService, KYCSelfServiceTokenService,
    KYCDocumentService,
)
from drf_spectacular.utils import extend_schema


# ============================================================
# Document Requirements
# ============================================================
class KYCDocumentRequirementViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = KYCDocumentRequirement.objects.none()
    serializer_class = KYCDocumentRequirementSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()


# ============================================================
# KYC Verifications
# ============================================================
class KYCVerificationViewSet(AuditLogMixin, OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = KYCVerification.objects.none()
    serializer_class = KYCVerificationSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    audit_entity_type = 'KYCVerification'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'client_type', 'client']
    search_fields = ['verification_number', 'client__first_name', 'client__last_name']
    ordering_fields = ['initiated_at', 'verified_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('client', 'initiated_by', 'reviewed_by').prefetch_related(
            'documents', 'checks', 'risk_assessment',
        )

    @action(detail=False, methods=['post'])
    def initiate(self, request):
        s = KYCInitiateSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            client = Client.objects.get(pk=s.validated_data['client'])
        except Client.DoesNotExist:
            return Response({'error': 'Client not found.'}, status=status.HTTP_404_NOT_FOUND)

        verification = KYCVerificationService.initiate(
            client, request.user, s.validated_data['client_type'],
        )
        return Response(KYCVerificationSerializer(verification).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def run_checks(self, request, pk=None):
        verification = self.get_object()
        s = KYCRunChecksSerializer(data=request.data); s.is_valid(raise_exception=True)
        KYCVerificationService.run_checks(verification, **s.validated_data)
        return Response(KYCVerificationSerializer(verification).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def verify(self, request, pk=None):
        verification = self.get_object()
        s = KYCVerifySerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            KYCVerificationService.verify(verification, request.user, s.validated_data['notes'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(KYCVerificationSerializer(verification).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticatedStaff, IsHQOrBranchManager])
    def reject(self, request, pk=None):
        verification = self.get_object()
        s = KYCRejectSerializer(data=request.data); s.is_valid(raise_exception=True)
        try:
            KYCVerificationService.reject(verification, request.user, s.validated_data['reason'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(KYCVerificationSerializer(verification).data)

    @action(detail=True, methods=['get'])
    def completion(self, request, pk=None):
        verification = self.get_object()
        return Response(KYCDocumentService.completion_status(verification))


# ============================================================
# Documents
# ============================================================
class KYCDocumentViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = KYCDocument.objects.none()
    serializer_class = KYCDocumentSerializer
    org_field = 'verification__organization'
    permission_classes = [IsAuthenticatedStaff]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


# ============================================================
# Checks (read-only)
# ============================================================
class KYCCheckViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = KYCCheck.objects.none()
    serializer_class = KYCCheckSerializer
    org_field = 'verification__organization'
    permission_classes = [IsAuthenticatedStaff]


# ============================================================
# Risk Assessments (read-only + recompute)
# ============================================================
class KYCRiskAssessmentViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = KYCRiskAssessment.objects.none()
    serializer_class = KYCRiskAssessmentSerializer
    org_field = 'verification__organization'
    permission_classes = [IsAuthenticatedStaff]

    @action(detail=True, methods=['post'])
    def recompute(self, request, pk=None):
        risk = self.get_object()
        KYCVerificationService.assess_risk(risk.verification)
        return Response(KYCRiskAssessmentSerializer(risk.verification.risk_assessment).data)


# ============================================================
# Review Schedule
# ============================================================
class KYCReviewScheduleViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = KYCReviewSchedule.objects.none()
    serializer_class = KYCReviewScheduleSerializer
    org_field = 'client__organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['risk_level', 'is_active']
    ordering_fields = ['next_review_due']


# ============================================================
# Self-Service
# ============================================================
class KYCSelfServiceViewSet(viewsets.ViewSet):
    """
    Generate one-time KYC submission tokens for clients.
    The client uses the token to submit their own KYC online.
    """
    permission_classes = [IsAuthenticatedStaff]
    serializer_class = SelfServiceTokenSerializer

    def get_serializer_class(self):
        """Return the serializer for schema generation."""
        return SelfServiceTokenSerializer

    @extend_schema(
        request=SelfServiceTokenSerializer,
        responses={201: SelfServiceTokenSerializer},
        tags=['KYC - Self Service'],
        summary='Generate a KYC self-service token',
        description=(
            'Creates a one-time link that a client can use to submit their '
            'KYC documents without logging into the platform. Send the '
            'resulting token to the client via SMS or WhatsApp.'
        ),
    )
    @action(detail=False, methods=['post'])
    def generate_token(self, request):
        client_id = request.data.get('client')
        try:
            client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            return Response(
                {'error': 'Client not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        token = KYCSelfServiceTokenService.generate(client, request.user)
        return Response(
            SelfServiceTokenSerializer(token).data,
            status=status.HTTP_201_CREATED,
        )