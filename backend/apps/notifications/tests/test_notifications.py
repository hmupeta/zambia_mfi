"""Tests for notification services — template rendering, phone normalization."""
from decimal import Decimal

import pytest

from apps.notifications.services import (
    render_template, normalize_phone, send_from_template,
)
from apps.notifications.models import NotificationTemplate, NotificationLog


pytestmark = pytest.mark.django_db


def test_normalize_phone_zambian_local():
    assert normalize_phone('0971234567') == '260971234567'


def test_normalize_phone_with_plus():
    assert normalize_phone('+260971234567') == '260971234567'


def test_normalize_phone_already_has_country_code():
    assert normalize_phone('260971234567') == '260971234567'


def test_normalize_phone_empty():
    assert normalize_phone('') == ''


def test_render_template_basic():
    body = 'Dear {{client_name}}, your balance is K{{balance_due}}.'
    out = render_template(body, {'client_name': 'John', 'balance_due': Decimal('500.00')})
    assert 'John' in out
    assert '500.00' in out


def test_render_template_missing_key_becomes_empty():
    body = 'Hello {{missing_key}}'
    out = render_template(body, {})
    assert 'Hello' in out
    assert '{{' not in out


def test_render_template_decimal_formatted(org):
    body = 'Amount: {{amount}}'
    out = render_template(body, {'amount': Decimal('1234.5678')})
    assert '1,234.57' in out


def test_send_from_template_creates_log(client, org, hq_admin, db):
    NotificationTemplate.objects.create(
        organization=org, key='test_hello', name='Hello', channel='SMS',
        body='Hi {{client_name}}', is_active=True,
    )
    logs = send_from_template(org, client, 'test_hello', sent_by=hq_admin)
    assert len(logs) == 1
    assert NotificationLog.objects.filter(client=client).exists()


def test_send_missing_template_returns_empty(client, org, db):
    logs = send_from_template(org, client, 'no_such_template')
    assert logs == []
