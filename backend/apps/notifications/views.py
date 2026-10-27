from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import IsAuthenticatedStaff, IsHQAdmin
from apps.core.mixins import OrganizationScopedMixin
from apps.clients.models import Client

from .models import NotificationChannelConfig, NotificationTemplate, NotificationLog
from .serializers import (
    NotificationChannelConfigSerializer, NotificationTemplateSerializer,
    NotificationLogSerializer, SendOneOffSerializer, SendBulkSerializer,
)
from .services import send_from_template, send_notification


class NotificationConfigViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = NotificationChannelConfig.objects.none()
    serializer_class = NotificationChannelConfigSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff, IsHQAdmin]
    filter_backends = []

    def get_queryset(self):
        return NotificationChannelConfig.objects.filter(
            organization=self.request.user.organization,
        )

    @action(detail=False, methods=['get', 'put', 'patch'])
    def current(self, request):
        config, _ = NotificationChannelConfig.objects.get_or_create(
            organization=request.user.organization,
        )
        if request.method == 'GET':
            return Response(NotificationChannelConfigSerializer(config).data)
        s = NotificationChannelConfigSerializer(config, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class NotificationTemplateViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.none()
    serializer_class = NotificationTemplateSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['channel', 'is_active']
    search_fields = ['key', 'name', 'body']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticatedStaff(), IsHQAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class NotificationLogViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = NotificationLog.objects.none()
    serializer_class = NotificationLogSerializer
    org_field = 'organization'
    permission_classes = [IsAuthenticatedStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['channel', 'status', 'client']
    search_fields = ['to_number', 'body', 'client__first_name', 'client__last_name']
    ordering_fields = ['created_at', 'sent_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        return qs.select_related('client', 'template', 'sent_by')

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'sent': qs.filter(status='SENT').count(),
            'failed': qs.filter(status='FAILED').count(),
            'sms': qs.filter(channel='SMS').count(),
            'whatsapp': qs.filter(channel='WHATSAPP').count(),
            'email': qs.filter(channel='EMAIL').count(),
        })


class NotificationSendViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticatedStaff]

    @action(detail=False, methods=['post'])
    def one_off(self, request):
        s = SendOneOffSerializer(data=request.data); s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            client = Client.objects.get(id=d['client'], organization=request.user.organization)
        except Client.DoesNotExist:
            return Response({'error': 'Client not found.'}, status=404)

        if d.get('template_key'):
            logs = send_from_template(
                request.user.organization, client, d['template_key'],
                context=d.get('context') or {},
                channels=[d['channel']], sent_by=request.user,
            )
            return Response(NotificationLogSerializer(logs, many=True).data, status=201)

        if not d.get('body'):
            return Response({'error': 'Body or template_key is required.'}, status=400)

        log = send_notification(
            org=request.user.organization, client=client,
            channel=d['channel'], body=d['body'],
            sent_by=request.user, context=d.get('context') or {},
        )
        return Response(NotificationLogSerializer(log).data, status=201)

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        s = SendBulkSerializer(data=request.data); s.is_valid(raise_exception=True)
        d = s.validated_data

        org = request.user.organization
        qs = Client.objects.filter(organization=org, is_active=True)
        if d.get('client_ids'):
            qs = qs.filter(id__in=d['client_ids'])
        if d.get('statuses'):
            qs = qs.filter(kyc_status__in=d['statuses'])

        if d['channel'] == 'BOTH':
            channels = ['SMS', 'WHATSAPP']
        elif d['channel'] == 'ALL':
            channels = ['SMS', 'WHATSAPP', 'EMAIL']
        else:
            channels = [d['channel']]

        total = 0
        for client in qs:
            total += len(send_from_template(org, client, d['template_key'],
                                            channels=channels, sent_by=request.user))
        return Response({'sent': total, 'clients': qs.count()})

    @action(detail=False, methods=['post'])
    def due_reminders(self, request):
        days = int(request.data.get('days_ahead', 3))
        from .triggers import send_due_reminders
        count = send_due_reminders(request.user.organization, days_ahead=days, user=request.user)
        return Response({'sent': count})
