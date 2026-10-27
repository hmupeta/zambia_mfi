"""Notification dispatch - templates, formatting, provider routing, logging."""
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

def _sanitize_context(ctx):
    """
    Recursively convert non-JSON-serializable values (Decimal, date/datetime)
    into strings so NotificationLog.context (a JSONField) can store them.

    Decimals are formatted with thousands separators and 2dp, matching what
    render_template() produces, so the stored context and the rendered body
    stay consistent.
    """
    from decimal import Decimal
    from datetime import date, datetime

    if ctx is None:
        return {}
    if isinstance(ctx, dict):
        return {k: _sanitize_context(v) for k, v in ctx.items()}
    if isinstance(ctx, (list, tuple)):
        return [_sanitize_context(v) for v in ctx]
    if isinstance(ctx, Decimal):
        return '{:,.2f}'.format(ctx)
    if isinstance(ctx, (datetime, date)):
        return ctx.isoformat()
    return ctx


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
    context = _sanitize_context(context)
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
