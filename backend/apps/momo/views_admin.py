# apps/momo/views_admin.py
import logging

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin
from apps.core.mixins import OrganizationScopedMixin

from .models import PaymentIntent, DisbursementIntent, MomoProviderConfig
from .serializers import (
    PaymentIntentSerializer,
    DisbursementIntentSerializer,
    MomoProviderConfigSerializer,
)
from .services import CollectionService, DisbursementService
from .providers.base import get_provider

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from apps.core.permissions import IsHQAdmin
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# PaymentIntent — read-only
# ═══════════════════════════════════════════════════════════
class PaymentIntentViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PaymentIntent.objects.none()
    serializer_class = PaymentIntentSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['provider_code', 'status', 'client', 'loan']
    search_fields = ['reference', 'provider_txn_id', 'phone',
                     'client__first_name', 'client__last_name']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('client', 'loan')

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'pending': qs.filter(status='PENDING').count(),
            'confirmed': qs.filter(status='CONFIRMED').count(),
            'failed': qs.filter(status='FAILED').count(),
            'pending_value': float(qs.filter(status='PENDING').aggregate(
                s=Sum('amount'))['s'] or 0),
            'confirmed_value': float(qs.filter(status='CONFIRMED').aggregate(
                s=Sum('amount'))['s'] or 0),
        })

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Re-run a failed intent's payment recording."""
        intent = self.get_object()
        if intent.status != 'CONFIRMED':
            return Response({'error': 'Only CONFIRMED intents can be retried.'}, status=400)
        if intent.payment_id:
            return Response({'error': 'Payment already recorded.'}, status=400)
        payment = CollectionService._record_payment(intent, request.user)
        if payment:
            return Response({'ok': True, 'payment_id': str(payment.id)})
        return Response({'error': 'Retry failed.'}, status=500)


# ═══════════════════════════════════════════════════════════
# DisbursementIntent — read-only
# ═══════════════════════════════════════════════════════════
class DisbursementIntentViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DisbursementIntent.objects.none()
    serializer_class = DisbursementIntentSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['provider_code', 'status', 'client', 'loan']
    search_fields = ['reference', 'provider_txn_id', 'phone',
                     'client__first_name', 'client__last_name']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('client', 'loan')

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'pending': qs.filter(status__in=['PENDING', 'PROCESSING']).count(),
            'completed': qs.filter(status='COMPLETED').count(),
            'failed': qs.filter(status='FAILED').count(),
        })


# ═══════════════════════════════════════════════════════════
# MomoProviderConfig — full CRUD + test action (HQ Admin only)
# ═══════════════════════════════════════════════════════════
class MomoConfigViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """
    CRUD for the requesting user's organization only.
    HQ Admins only — Branch Managers and below cannot edit provider credentials.
    Extended with a `test` action that pings the provider.
    """
    queryset = MomoProviderConfig.objects.none()
    serializer_class = MomoProviderConfigSerializer
    org_field = 'organization'
    permission_classes = [IsHQAdmin]

    def get_queryset(self):
        return super().get_queryset().filter(
            organization=self.request.user.organization,
        ).order_by('provider_code')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    @action(detail=True, methods=['post'], url_path='test')
    def test_connection(self, request, pk=None):
        """
        POST /api/momo/configs/{id}/test/

        Instantiate the provider with this config's credentials and
        call test_connection(). Never raises — returns
        {ok: bool, message: str} with 200 or 400.
        """
        config = self.get_object()

        try:
            provider = get_provider(config)
        except Exception as e:
            logger.warning(
                'test_connection: provider init failed for %s: %s',
                config.id, e,
            )
            return Response(
                {'ok': False, 'message': f'Provider not available: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = provider.test_connection()
        except AttributeError:
            return Response(
                {
                    'ok': False,
                    'message': (
                        f'{provider.name} does not implement test_connection().'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception('test_connection crashed for %s', config.id)
            return Response(
                {'ok': False, 'message': f'Unexpected error: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=200 if result.get('ok') else 400)
    # apps/momo/views_admin.py — inside MomoConfigViewSet

    @action(detail=True, methods=['post'], url_path='test')
    def test_connection(self, request, pk=None):
        config = self.get_object()
        try:
            provider = get_provider(config)
        except Exception as e:
            return Response({'ok': False, 'message': f'Provider not available: {e}'},
                            status=400)
        try:
            result = provider.test_connection()
        except AttributeError:
            return Response({'ok': False,
                            'message': f'{provider.name} does not implement test_connection().'},
                            status=400)
        except Exception as e:
            return Response({'ok': False, 'message': f'Unexpected error: {e}'},
                            status=400)
        return Response(result, status=200 if result.get('ok') else 400)


@api_view(['POST'])
@permission_classes([IsHQAdmin])
def provision_mtn_sandbox(request):
    """
    POST /api/momo/provision-mtn-sandbox/
    Body: {"subscription_key": "...", "callback_host": "..."}

    Creates an MTN sandbox API User and API Key. Returns the credentials
    so the frontend can populate the form. Nothing is saved here — the
    user still has to click Save on the form to persist.
    """
    from apps.mtn.sandbox import (
        provision_sandbox_user, SandboxProvisioningError,
    )

    subscription_key = (request.data.get('subscription_key') or '').strip()
    callback_host = (request.data.get('callback_host') or 'localhost').strip()

    if not subscription_key:
        return Response(
            {'error': 'Subscription key is required to provision sandbox credentials.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = provision_sandbox_user(subscription_key, callback_host)
    except SandboxProvisioningError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    AuditLog.objects.create(
        organization=request.user.organization,
        user=request.user,
        action='MTN_SANDBOX_PROVISIONED',
        entity_type='MomoProviderConfig',
        new_values={'api_user': result['api_user']},
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return Response({
        'ok': True,
        'api_user': result['api_user'],
        'api_key': result['api_key'],
    })