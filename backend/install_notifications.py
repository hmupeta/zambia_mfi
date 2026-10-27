#!/usr/bin/env python3
"""
Installer for the Notifications module (SMS + WhatsApp + Email).
Run from the backend/ directory:   python install_notifications.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
APP  = ROOT / "apps" / "notifications"
PROV = APP / "providers"
MGMT = APP / "management"
CMD  = MGMT / "commands"
MIG  = APP / "migrations"
TPL  = ROOT.parent / "frontend" / "templates" / "app" / "notifications"

FILES = []
def add(path, content):
    FILES.append((path, content))

# ═════════════════════════════════════════════
# Package inits
# ═════════════════════════════════════════════
add(APP  / "__init__.py", "")
add(PROV / "__init__.py", "")
add(MGMT / "__init__.py", "")
add(CMD  / "__init__.py", "")
add(MIG  / "__init__.py", "")

# ═════════════════════════════════════════════
# apps.py
# ═════════════════════════════════════════════
add(APP / "apps.py", r'''from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    label = 'notifications'
''')

# ═════════════════════════════════════════════
# models.py
# ═════════════════════════════════════════════
add(APP / "models.py", r'''import uuid
from django.db import models

from apps.core.models import Organization
from apps.clients.models import Client


CHANNEL_CHOICES = [
    ('SMS', 'SMS'),
    ('WHATSAPP', 'WhatsApp'),
    ('EMAIL', 'Email'),
]

STATUS_CHOICES = [
    ('QUEUED', 'Queued'),
    ('SENT', 'Sent'),
    ('DELIVERED', 'Delivered'),
    ('FAILED', 'Failed'),
]

PROVIDER_CHOICES = [
    ('AFRICAS_TALKING', "Africa's Talking"),
    ('TWILIO', 'Twilio'),
    ('META_CLOUD', 'Meta WhatsApp Cloud'),
    ('SMTP', 'SMTP'),
    ('SENDGRID', 'SendGrid'),
    ('NONE', 'None'),
]


class NotificationChannelConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='notification_config',
    )

    sms_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='AFRICAS_TALKING')
    sms_username = models.CharField(max_length=100, blank=True)
    sms_api_key = models.CharField(max_length=200, blank=True)
    sms_sender_id = models.CharField(max_length=20, blank=True)

    whatsapp_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='TWILIO')
    twilio_account_sid = models.CharField(max_length=100, blank=True)
    twilio_auth_token = models.CharField(max_length=200, blank=True)
    whatsapp_from = models.CharField(max_length=50, blank=True)

    email_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='SMTP')
    email_host = models.CharField(max_length=200, blank=True)
    email_port = models.PositiveIntegerField(default=587)
    email_username = models.CharField(max_length=200, blank=True)
    email_password = models.CharField(max_length=200, blank=True)
    email_use_tls = models.BooleanField(default=True)
    email_from_name = models.CharField(max_length=100, blank=True)
    email_from_address = models.CharField(max_length=200, blank=True)

    is_active = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)
    test_number = models.CharField(max_length=200, blank=True)
    default_country_code = models.CharField(max_length=5, default='260')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_channel_configs'

    def __str__(self):
        return f'Notification config - {self.organization.code}'


class NotificationTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='notification_templates',
    )
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=100)
    channel = models.CharField(
        max_length=20,
        choices=[
            ('SMS', 'SMS'),
            ('WHATSAPP', 'WhatsApp'),
            ('EMAIL', 'Email'),
            ('BOTH', 'SMS + WhatsApp'),
            ('ALL', 'All Channels'),
        ],
        default='SMS',
    )
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_templates'
        ordering = ['key']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'key'],
                name='unique_notification_template_key_per_org',
            ),
        ]

    def __str__(self):
        return f'{self.key} - {self.name}'


class NotificationLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='notification_logs',
    )
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True,
    )
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications',
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    to_number = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')
    provider = models.CharField(max_length=30, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    sent_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications_sent',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['channel']),
        ]

    def __str__(self):
        return f'{self.channel} -> {self.to_number} [{self.status}]'
''')

# ═════════════════════════════════════════════
# admin.py
# ═════════════════════════════════════════════
add(APP / "admin.py", r'''from django.contrib import admin
from .models import NotificationChannelConfig, NotificationTemplate, NotificationLog


@admin.register(NotificationChannelConfig)
class NotificationChannelConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'sms_provider', 'whatsapp_provider', 'email_provider', 'is_active', 'is_sandbox']
    list_filter = ['is_active', 'is_sandbox']
    search_fields = ['organization__code']


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'channel', 'is_active', 'organization']
    list_filter = ['channel', 'is_active']
    search_fields = ['key', 'name', 'body', 'subject']


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'channel', 'to_number', 'client', 'status', 'provider']
    list_filter = ['channel', 'status', 'provider']
    search_fields = ['to_number', 'body']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['id', 'created_at', 'sent_at', 'context']
''')

# ═════════════════════════════════════════════
# providers/sms.py
# ═════════════════════════════════════════════
add(PROV / "sms.py", r'''"""Africa's Talking SMS adapter."""
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

AT_LIVE = 'https://api.africastalking.com/version1/messaging'
AT_SANDBOX = 'https://api.sandbox.africastalking.com/version1/messaging'


class SMSResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def send_sms(to_number, message, config):
    username = (config.sms_username or '').strip()
    api_key = (config.sms_api_key or '').strip()
    sender_id = (config.sms_sender_id or '').strip()

    if not username or not api_key:
        return SMSResult(False, error="Africa's Talking credentials not configured.")

    url = AT_SANDBOX if config.is_sandbox else AT_LIVE

    payload = {'username': username, 'to': to_number, 'message': message}
    if sender_id:
        payload['from'] = sender_id

    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('apiKey', api_key)
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            parsed = json.loads(resp.read().decode('utf-8'))
            recipients = parsed.get('SMSMessageData', {}).get('Recipients', [])
            if recipients:
                r = recipients[0]
                if r.get('status', '').lower() == 'success':
                    return SMSResult(True, message_id=r.get('messageId', ''))
                return SMSResult(False, error=r.get('status', 'Unknown'))
            return SMSResult(False, error='No recipients in response')
    except Exception as e:
        logger.warning("SMS failed to %s: %s", to_number, e)
        return SMSResult(False, error=str(e))
''')

# ═════════════════════════════════════════════
# providers/whatsapp.py
# ═════════════════════════════════════════════
add(PROV / "whatsapp.py", r'''"""Twilio WhatsApp adapter."""
import base64
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class WhatsAppResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def send_whatsapp(to_number, message, config):
    account_sid = (config.twilio_account_sid or '').strip()
    auth_token = (config.twilio_auth_token or '').strip()
    from_number = (config.whatsapp_from or '').strip()

    if not account_sid or not auth_token:
        return WhatsAppResult(False, error='Twilio credentials not configured.')
    if not from_number:
        return WhatsAppResult(False, error='WhatsApp From number not configured.')

    if not from_number.startswith('whatsapp:'):
        from_number = 'whatsapp:' + from_number
    to_whatsapp = to_number if to_number.startswith('whatsapp:') else 'whatsapp:' + to_number

    url = 'https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json' % account_sid
    payload = {'From': from_number, 'To': to_whatsapp, 'Body': message}
    data = urllib.parse.urlencode(payload).encode('utf-8')

    creds = base64.b64encode(('%s:%s' % (account_sid, auth_token)).encode()).decode()

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Basic ' + creds)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            parsed = json.loads(resp.read().decode('utf-8'))
            sid = parsed.get('sid', '')
            if sid:
                return WhatsAppResult(True, message_id=sid)
            return WhatsAppResult(False, error='Unexpected: %s' % parsed.get('status'))
    except Exception as e:
        logger.warning("WhatsApp failed to %s: %s", to_number, e)
        return WhatsAppResult(False, error=str(e))
''')

# ═════════════════════════════════════════════
# providers/email.py
# ═════════════════════════════════════════════
add(PROV / "email.py", r'''"""SMTP email adapter."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def send_email(to_address, subject, body, config):
    if not to_address or '@' not in to_address:
        return EmailResult(False, error='Invalid email: ' + str(to_address))
    if not config.email_host:
        return EmailResult(False, error='SMTP host not configured.')
    if not config.email_from_address:
        return EmailResult(False, error='From address not configured.')

    from_name = (config.email_from_name or '').strip()
    from_addr = config.email_from_address
    from_header = (from_name + ' <' + from_addr + '>') if from_name else from_addr

    msg = EmailMessage()
    msg['Subject'] = subject or 'Notification'
    msg['From'] = from_header
    msg['To'] = to_address
    msg.set_content(body or '')
    msg.add_alternative('<pre style="font-family: inherit;">' + (body or '') + '</pre>', subtype='html')

    try:
        if config.email_use_tls:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(config.email_host, config.email_port, timeout=15) as smtp:
                smtp.starttls(context=ctx)
                if config.email_username:
                    smtp.login(config.email_username, config.email_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(config.email_host, config.email_port, timeout=15) as smtp:
                if config.email_username:
                    smtp.login(config.email_username, config.email_password)
                smtp.send_message(msg)
        return EmailResult(True, message_id=msg['Message-ID'] or '')
    except Exception as e:
        logger.warning("Email failed to %s: %s", to_address, e)
        return EmailResult(False, error=str(e))
''')

# ═════════════════════════════════════════════
# services.py
# ═════════════════════════════════════════════
add(APP / "services.py", r'''"""Notification dispatch - templates, formatting, provider routing, logging."""
import logging
import re
from decimal import Decimal

from django.utils import timezone

from .models import (
    NotificationChannelConfig, NotificationTemplate, NotificationLog,
)
from .providers.sms import send_sms
from .providers.whatsapp import send_whatsapp
from .providers.email import send_email

logger = logging.getLogger(__name__)


def normalize_phone(raw, country_code='260'):
    if not raw:
        return ''
    digits = re.sub(r'[^\d]', '', str(raw))
    if not digits:
        return ''
    if digits.startswith(country_code) and len(digits) >= 11:
        return digits
    if digits.startswith('0'):
        return country_code + digits[1:]
    if len(digits) == 9:
        return country_code + digits
    return digits


_PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}')


def render_template(body, context):
    def repl(match):
        value = context.get(match.group(1), '')
        if value is None:
            return ''
        if isinstance(value, Decimal):
            return '{:,.2f}'.format(value)
        return str(value)
    return _PLACEHOLDER_RE.sub(repl, body or '')


def get_template(org, key):
    return NotificationTemplate.objects.filter(
        organization=org, key=key, is_active=True,
    ).first()


def _config_for(org):
    config, _ = NotificationChannelConfig.objects.get_or_create(organization=org)
    return config


def _destination(client, config, channel):
    if channel in ('SMS', 'WHATSAPP') and config.is_sandbox and config.test_number:
        return normalize_phone(config.test_number, config.default_country_code or '260')
    if channel == 'EMAIL':
        if config.is_sandbox and config.test_number and '@' in config.test_number:
            return config.test_number
        return (client.email or '').strip()
    return normalize_phone(client.phone, config.default_country_code or '260')


def send_notification(org, client, channel, body, template=None, sent_by=None, context=None):
    config = _config_for(org)

    if not config.is_active:
        return NotificationLog.objects.create(
            organization=org, template=template, client=client,
            channel=channel, to_number='', body=body,
            status='FAILED', provider='NONE',
            error='Notifications disabled for this organization.',
            context=context or {}, sent_by=sent_by,
        )

    to_number = _destination(client, config, channel)
    if not to_number:
        return NotificationLog.objects.create(
            organization=org, template=template, client=client,
            channel=channel, to_number='', body=body,
            status='FAILED', provider='NONE',
            error='Client has no email address.' if channel == 'EMAIL' else 'Client has no phone number.',
            context=context or {}, sent_by=sent_by,
        )

    log = NotificationLog.objects.create(
        organization=org, template=template, client=client,
        channel=channel, to_number=to_number, body=body,
        status='QUEUED', context=context or {}, sent_by=sent_by,
    )

    if channel == 'SMS':
        result = send_sms(to_number, body, config)
        log.provider = config.sms_provider or 'AFRICAS_TALKING'
    elif channel == 'WHATSAPP':
        result = send_whatsapp(to_number, body, config)
        log.provider = config.whatsapp_provider or 'TWILIO'
    elif channel == 'EMAIL':
        subject = (template.subject if template else '') or 'Notification'
        subject = render_template(subject, context or {})
        result = send_email(to_number, subject, body, config)
        log.provider = config.email_provider or 'SMTP'
    else:
        log.status = 'FAILED'
        log.error = 'Unknown channel: ' + channel
        log.save()
        return log

    if result.success:
        log.status = 'SENT'
        log.provider_message_id = result.message_id or ''
        log.sent_at = timezone.now()
    else:
        log.status = 'FAILED'
        log.error = result.error or 'Unknown error'

    log.save()
    return log


def send_from_template(org, client, template_key, context=None, channels=None, sent_by=None):
    template = get_template(org, template_key)
    if not template:
        logger.warning('No active template for key=%s org=%s', template_key, org.code)
        return []

    ctx = dict(context or {})
    ctx.setdefault('client_name', (client.first_name + ' ' + client.last_name).strip())
    ctx.setdefault('client_first_name', client.first_name or '')
    ctx.setdefault('client_nrc', client.nrc or '')
    ctx.setdefault('org_name', getattr(org, 'name', org.code))

    body = render_template(template.body, ctx)

    if channels is None:
        if template.channel == 'BOTH':
            channels = ['SMS', 'WHATSAPP']
        elif template.channel == 'ALL':
            channels = ['SMS', 'WHATSAPP', 'EMAIL']
        else:
            channels = [template.channel]

    logs = []
    for ch in channels:
        logs.append(send_notification(
            org=org, client=client, channel=ch, body=body,
            template=template, sent_by=sent_by, context=ctx,
        ))
    return logs
''')

# ═════════════════════════════════════════════
# triggers.py
# ═════════════════════════════════════════════
add(APP / "triggers.py", r'''"""Auto-triggers. Failures never break callers."""
import logging

logger = logging.getLogger(__name__)


def on_payment_received(payment):
    try:
        from .services import send_from_template
        client = payment.client
        org = payment.organization
        ctx = {
            'amount': payment.amount,
            'loan_number': payment.loan.loan_number if payment.loan else '',
            'payment_number': payment.payment_number,
            'balance_due': payment.loan.balance_due if payment.loan else 0,
            'date': payment.received_at.strftime('%d %b %Y') if payment.received_at else '',
        }
        send_from_template(org=org, client=client, template_key='payment_received',
                           context=ctx, sent_by=payment.received_by)
        if client.email:
            send_from_template(org=org, client=client, template_key='payment_received_email',
                               context=ctx, channels=['EMAIL'], sent_by=payment.received_by)
    except Exception as e:
        logger.warning('payment_received notification failed: %s', e)


def on_loan_disbursed(loan, user=None):
    try:
        from .services import send_from_template
        first_due = ''
        if loan.installments.exists():
            fi = loan.installments.order_by('due_date').first()
            first_due = fi.due_date.strftime('%d %b %Y')
        ctx = {
            'amount': loan.disbursed_amount or loan.amount,
            'loan_number': loan.loan_number,
            'maturity_date': loan.maturity_date.strftime('%d %b %Y') if loan.maturity_date else '',
            'first_due_date': first_due,
        }
        send_from_template(org=loan.organization, client=loan.client,
                           template_key='loan_disbursed', context=ctx, sent_by=user)
        if loan.client.email:
            send_from_template(org=loan.organization, client=loan.client,
                               template_key='loan_disbursed_email', context=ctx,
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('loan_disbursed notification failed: %s', e)


def on_kyc_approved(client, user=None):
    try:
        from .services import send_from_template
        send_from_template(org=client.organization, client=client,
                           template_key='kyc_approved', context={}, sent_by=user)
        if client.email:
            send_from_template(org=client.organization, client=client,
                               template_key='kyc_approved_email', context={},
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('kyc_approved notification failed: %s', e)


def on_application_approved(application, user=None):
    try:
        from .services import send_from_template
        ctx = {
            'amount': application.requested_amount,
            'application_number': application.application_number,
        }
        send_from_template(org=application.organization, client=application.client,
                           template_key='application_approved', context=ctx, sent_by=user)
        if application.client.email:
            send_from_template(org=application.organization, client=application.client,
                               template_key='application_approved_email', context=ctx,
                               channels=['EMAIL'], sent_by=user)
    except Exception as e:
        logger.warning('application_approved notification failed: %s', e)


def send_due_reminders(org, days_ahead=3, user=None):
    from datetime import timedelta
    from django.utils import timezone
    from apps.loans.models import LoanInstallment
    from .services import send_from_template

    target = timezone.now().date() + timedelta(days=days_ahead)
    qs = LoanInstallment.objects.filter(
        is_paid=False, due_date=target,
        loan__organization=org, loan__is_fully_repaid=False,
    ).select_related('loan', 'loan__client')

    sent = 0
    for inst in qs:
        client = inst.loan.client
        ctx = {
            'amount': inst.total_due - inst.paid_amount,
            'due_date': inst.due_date.strftime('%d %b %Y'),
            'loan_number': inst.loan.loan_number,
            'installment_no': inst.installment_no,
        }
        key = 'due_reminder_%dd' % days_ahead
        sent += len(send_from_template(org, client, key, context=ctx, sent_by=user))
        if client.email:
            sent += len(send_from_template(org, client, 'due_reminder_email',
                                           context=ctx, channels=['EMAIL'], sent_by=user))
    return sent
''')

# ═════════════════════════════════════════════
# serializers.py
# ═════════════════════════════════════════════
add(APP / "serializers.py", r'''from rest_framework import serializers
from .models import NotificationChannelConfig, NotificationTemplate, NotificationLog


class NotificationChannelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannelConfig
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'updated_at']


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at', 'is_system']


class NotificationLogSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    template_key = serializers.CharField(source='template.key', read_only=True)
    sent_by_name = serializers.CharField(source='sent_by.get_full_name', read_only=True)

    class Meta:
        model = NotificationLog
        fields = '__all__'

    def get_client_name(self, obj):
        if not obj.client:
            return ''
        return (obj.client.first_name + ' ' + obj.client.last_name).strip()


class SendOneOffSerializer(serializers.Serializer):
    client = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=['SMS', 'WHATSAPP', 'EMAIL'])
    body = serializers.CharField(required=False, allow_blank=True)
    subject = serializers.CharField(required=False, allow_blank=True, default='')
    template_key = serializers.CharField(required=False, allow_blank=True)
    context = serializers.DictField(required=False, default=dict)


class SendBulkSerializer(serializers.Serializer):
    template_key = serializers.CharField()
    channel = serializers.ChoiceField(choices=['SMS', 'WHATSAPP', 'EMAIL', 'BOTH', 'ALL'])
    client_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    statuses = serializers.ListField(child=serializers.CharField(), required=False)
''')

# ═════════════════════════════════════════════
# views.py
# ═════════════════════════════════════════════
add(APP / "views.py", r'''from rest_framework import viewsets, filters
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
''')

# ═════════════════════════════════════════════
# views_pages.py
# ═════════════════════════════════════════════
add(APP / "views_pages.py", r'''from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def notifications_list(request):
    return render(request, 'app/notifications/list.html')


@never_cache
def notifications_templates(request):
    return render(request, 'app/notifications/templates.html')


@never_cache
def notifications_settings(request):
    return render(request, 'app/notifications/settings.html')
''')

# ═════════════════════════════════════════════
# urls.py
# ═════════════════════════════════════════════
add(APP / "urls.py", r'''from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationConfigViewSet, NotificationTemplateViewSet,
    NotificationLogViewSet, NotificationSendViewSet,
)

router = DefaultRouter()
router.register(r'config', NotificationConfigViewSet, basename='notification-config')
router.register(r'templates', NotificationTemplateViewSet, basename='notification-template')
router.register(r'logs', NotificationLogViewSet, basename='notification-log')
router.register(r'send', NotificationSendViewSet, basename='notification-send')

urlpatterns = [path('', include(router.urls))]
''')

add(APP / "urls_pages.py", r'''from django.urls import path
from . import views_pages

urlpatterns = [
    path('notifications/', views_pages.notifications_list, name='notifications-list-page'),
    path('notifications/templates/', views_pages.notifications_templates, name='notifications-templates-page'),
    path('notifications/settings/', views_pages.notifications_settings, name='notifications-settings-page'),
]
''')

# ═════════════════════════════════════════════
# seed_notification_templates.py
# ═════════════════════════════════════════════
add(CMD / "seed_notification_templates.py", r'''"""Seed default notification templates."""
from django.core.management.base import BaseCommand

from apps.core.models import Organization
from apps.notifications.models import NotificationTemplate


DEFAULTS = [
    ('payment_received', 'Payment Received', 'SMS', '',
     'Dear {{client_name}}, we have received your payment of K{{amount}} for loan {{loan_number}} on {{date}}. New balance: K{{balance_due}}. Thank you.'),
    ('loan_disbursed', 'Loan Disbursed', 'SMS', '',
     'Dear {{client_name}}, your loan {{loan_number}} of K{{amount}} has been disbursed. First payment due {{first_due_date}}. Thank you.'),
    ('due_reminder_3d', 'Due Reminder (3 days)', 'SMS', '',
     'Dear {{client_name}}, a payment of K{{amount}} for loan {{loan_number}} is due on {{due_date}}. Please ensure funds are ready.'),
    ('due_reminder_1d', 'Due Reminder (1 day)', 'SMS', '',
     'Dear {{client_name}}, reminder: K{{amount}} due TOMORROW ({{due_date}}) for loan {{loan_number}}.'),
    ('due_reminder_0d', 'Due Reminder (today)', 'SMS', '',
     'Dear {{client_name}}, your payment of K{{amount}} for loan {{loan_number}} is due TODAY. Please pay to avoid penalties.'),
    ('overdue_notice', 'Overdue Notice', 'SMS', '',
     'Dear {{client_name}}, your payment of K{{amount}} for loan {{loan_number}} was due on {{due_date}} and is now overdue. Please pay immediately.'),
    ('kyc_approved', 'KYC Verified', 'SMS', '',
     'Dear {{client_name}}, your KYC verification is complete. You can now apply for loans.'),
    ('application_approved', 'Application Approved', 'SMS', '',
     'Dear {{client_name}}, your loan application {{application_number}} for K{{amount}} has been approved. We will contact you shortly.'),

    ('payment_received_email', 'Payment Received (Email)', 'EMAIL',
     'Payment confirmation - {{org_name}}',
     'Dear {{client_name}},\n\nWe have received your payment of K{{amount}} for loan {{loan_number}} on {{date}}.\n\nNew outstanding balance: K{{balance_due}}\n\nThank you.\n\nRegards,\n{{org_name}}'),
    ('loan_disbursed_email', 'Loan Disbursed (Email)', 'EMAIL',
     'Your loan has been disbursed - {{org_name}}',
     'Dear {{client_name}},\n\nYour loan {{loan_number}} of K{{amount}} has been disbursed.\n\nFirst payment due date: {{first_due_date}}\n\nRegards,\n{{org_name}}'),
    ('due_reminder_email', 'Due Reminder (Email)', 'EMAIL',
     'Upcoming payment reminder - {{org_name}}',
     'Dear {{client_name}},\n\nThis is a friendly reminder that a payment of K{{amount}} for loan {{loan_number}} is due on {{due_date}}.\n\nRegards,\n{{org_name}}'),
    ('overdue_notice_email', 'Overdue Notice (Email)', 'EMAIL',
     'Overdue payment on loan {{loan_number}} - {{org_name}}',
     'Dear {{client_name}},\n\nYour payment of K{{amount}} for loan {{loan_number}} was due on {{due_date}} and is now overdue.\n\nPlease settle the outstanding balance as soon as possible.\n\nRegards,\n{{org_name}}'),
    ('kyc_approved_email', 'KYC Verified (Email)', 'EMAIL',
     'KYC verification complete - {{org_name}}',
     'Dear {{client_name}},\n\nWe are pleased to confirm that your KYC verification is complete.\n\nRegards,\n{{org_name}}'),
    ('application_approved_email', 'Application Approved (Email)', 'EMAIL',
     'Your loan application has been approved - {{org_name}}',
     'Dear {{client_name}},\n\nYour loan application {{application_number}} for K{{amount}} has been approved.\n\nRegards,\n{{org_name}}'),
]


class Command(BaseCommand):
    help = 'Seed default notification templates'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, help='Organization code (default: all)')

    def handle(self, *args, **options):
        qs = Organization.objects.all()
        if options.get('org'):
            qs = qs.filter(code=options['org'])

        total = 0
        for org in qs:
            for key, name, channel, subject, body in DEFAULTS:
                _, created = NotificationTemplate.objects.get_or_create(
                    organization=org, key=key,
                    defaults={
                        'name': name, 'channel': channel, 'subject': subject,
                        'body': body, 'is_active': True, 'is_system': True,
                    },
                )
                if created:
                    total += 1
                    self.stdout.write('  + %s / %s' % (org.code, key))

        self.stdout.write(self.style.SUCCESS('Created %d templates.' % total))
''')

# ═════════════════════════════════════════════
# Write
# ═════════════════════════════════════════════
def main():
    print("Writing notification module files...")
    for path, content in FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        print("  + %s" % rel)
    print("\nDone. %d files written." % len(FILES))
    print("\nNext steps:")
    print("  1. Add to config/urls.py:   path('app/', include('apps.notifications.urls_pages')),")
    print("  2. python manage.py makemigrations notifications")
    print("  3. python manage.py migrate")
    print("  4. python manage.py seed_notification_templates")


if __name__ == "__main__":
    main()