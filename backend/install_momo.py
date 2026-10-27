#!/usr/bin/env python3
"""Installer for Phase AK — Mobile Money Integration.
Run from backend/:   python install_momo.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
APP = ROOT / "apps" / "momo"
PROV = APP / "providers"
TESTS = APP / "tests"
CMD = APP / "management" / "commands"

FILES = []
def add(path, content):
    FILES.append((path, content))

# ═════════════════════════════════════════════
# apps.py
# ═════════════════════════════════════════════
add(APP / "apps.py", r'''from django.apps import AppConfig


class MomoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.momo'
    label = 'momo'
''')

# ═════════════════════════════════════════════
# models.py
# ═════════════════════════════════════════════
add(APP / "models.py", r'''import uuid

from django.db import models
from django.utils import timezone


PROVIDER_CHOICES = [
    ('FAKE', 'Fake (Testing)'),
    ('MTN_MOMO', 'MTN Mobile Money'),
    ('AIRTEL_MONEY', 'Airtel Money'),
    ('CELLULANT', 'Cellulant Tingg'),
    ('FLUTTERWAVE', 'Flutterwave'),
]

PAYMENT_INTENT_STATUS = [
    ('PENDING', 'Pending'),
    ('CONFIRMED', 'Confirmed'),
    ('FAILED', 'Failed'),
    ('EXPIRED', 'Expired'),
    ('CANCELLED', 'Cancelled'),
]

DISBURSEMENT_INTENT_STATUS = [
    ('PENDING', 'Pending'),
    ('PROCESSING', 'Processing'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
    ('CANCELLED', 'Cancelled'),
]


class MomoProviderConfig(models.Model):
    """Per-organization credentials for a mobile money provider."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='momo_configs',
    )
    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    display_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)

    # API credentials (structure varies by provider)
    api_key = models.CharField(max_length=500, blank=True)
    api_secret = models.CharField(max_length=500, blank=True)
    merchant_id = models.CharField(max_length=200, blank=True)
    short_code = models.CharField(max_length=50, blank=True)
    subscription_key = models.CharField(max_length=500, blank=True)

    # Webhook / callback
    webhook_secret = models.CharField(max_length=500, blank=True)
    callback_url = models.URLField(blank=True)

    # GL account codes used by this provider
    collection_gl_code = models.CharField(
        max_length=10, default='1030',
        help_text='GL code for inbound collections (Debit).',
    )
    disbursement_gl_code = models.CharField(
        max_length=10, default='1030',
        help_text='GL code for outbound payouts (Credit).',
    )

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'momo_provider_configs'
        unique_together = [('organization', 'provider_code')]

    def __str__(self):
        return f'{self.organization.code} - {self.provider_code}'


class PaymentIntent(models.Model):
    """An inbound mobile money payment awaiting provider confirmation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='payment_intents',
    )
    branch = models.ForeignKey(
        'core.Branch', on_delete=models.PROTECT, null=True, blank=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.PROTECT,
        related_name='payment_intents', null=True, blank=True,
    )
    payment = models.OneToOneField(
        'payments.Payment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='momo_intent',
    )

    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    reference = models.CharField(max_length=60, unique=True, db_index=True)
    provider_txn_id = models.CharField(
        max_length=200, blank=True, db_index=True,
        help_text='Provider transaction ID. Unique per provider.',
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    phone = models.CharField(max_length=30, help_text='Payer phone number.')

    status = models.CharField(
        max_length=20, choices=PAYMENT_INTENT_STATUS, default='PENDING',
        db_index=True,
    )
    error = models.TextField(blank=True)

    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'momo_payment_intents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['provider_code', 'provider_txn_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider_code', 'provider_txn_id'],
                condition=models.Q(provider_txn_id__gt=''),
                name='unique_momo_provider_txn_per_provider',
            ),
        ]

    def __str__(self):
        return f'{self.reference} - {self.amount} ({self.status})'

    def save(self, *args, **kwargs):
        if self.client_id and not self.organization_id:
            self.organization_id = self.client.organization_id
        if self.client_id and not self.branch_id:
            self.branch_id = self.client.branch_id
        super().save(*args, **kwargs)


class DisbursementIntent(models.Model):
    """Outbound mobile money payout to a client."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE,
        related_name='disbursement_intents',
    )
    branch = models.ForeignKey(
        'core.Branch', on_delete=models.PROTECT, null=True, blank=True,
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT,
        related_name='disbursement_intents',
    )
    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.PROTECT,
        related_name='disbursement_intents', null=True, blank=True,
    )
    journal_entry = models.ForeignKey(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='disbursement_intents',
    )

    provider_code = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    reference = models.CharField(max_length=60, unique=True, db_index=True)
    provider_txn_id = models.CharField(max_length=200, blank=True, db_index=True)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    phone = models.CharField(max_length=30, help_text='Recipient phone number.')

    status = models.CharField(
        max_length=20, choices=DISBURSEMENT_INTENT_STATUS, default='PENDING',
        db_index=True,
    )
    error = models.TextField(blank=True)

    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    initiated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'momo_disbursement_intents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['provider_code', 'provider_txn_id']),
        ]

    def __str__(self):
        return f'{self.reference} - {self.amount} ({self.status})'

    def save(self, *args, **kwargs):
        if self.client_id and not self.organization_id:
            self.organization_id = self.client.organization_id
        if self.client_id and not self.branch_id:
            self.branch_id = self.client.branch_id
        super().save(*args, **kwargs)
''')

# ═════════════════════════════════════════════
# providers/base.py — abstract adapter
# ═════════════════════════════════════════════
add(PROV / "base.py", r'''"""
Abstract mobile money provider adapter.

Each provider (MTN, Airtel, Cellulant, etc.) implements this interface.
Services call these methods; they never touch provider-specific code.
"""
from abc import ABC, abstractmethod


class MomoProviderError(Exception):
    """Raised when a provider call fails."""
    def __init__(self, message, code='', raw=None):
        super().__init__(message)
        self.code = code
        self.raw = raw or {}


class BaseMomoProvider(ABC):
    """
    Interface every provider adapter must implement.
    All methods must return a dict with a consistent shape.
    """

    code = 'BASE'
    name = 'Base Provider'

    def __init__(self, config):
        """`config` is a MomoProviderConfig instance."""
        self.config = config

    # ----------------------------------------------------------
    # Inbound collections
    # ----------------------------------------------------------
    @abstractmethod
    def collect(self, reference, amount, phone, description=''):
        """
        Request a payment FROM the client.

        Returns:
            {
                'provider_txn_id': str,     # provider's tracking ID
                'status': str,              # PENDING | CONFIRMED | FAILED
                'raw': dict,                # full response body
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Outbound disbursements
    # ----------------------------------------------------------
    @abstractmethod
    def disburse(self, reference, amount, phone, description=''):
        """
        Send money TO the client's wallet.

        Returns:
            {
                'provider_txn_id': str,
                'status': str,              # PROCESSING | COMPLETED | FAILED
                'raw': dict,
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Webhook verification
    # ----------------------------------------------------------
    @abstractmethod
    def verify_webhook(self, headers, body_bytes):
        """
        Verify the authenticity of an inbound webhook.

        Returns:
            bool    — True if the signature is valid.

        Common implementations:
            - HMAC SHA256 header comparison
            - Bearer token comparison
            - IP allowlist
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Webhook parsing
    # ----------------------------------------------------------
    @abstractmethod
    def parse_webhook(self, payload):
        """
        Normalize a provider webhook into a consistent shape.

        Returns:
            {
                'provider_txn_id': str,
                'status': str,              # CONFIRMED | FAILED
                'amount': Decimal | None,
                'phone': str | None,
                'error': str,
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Optional: balance query
    # ----------------------------------------------------------
    def get_balance(self):
        """Optional: fetch merchant float balance."""
        raise NotImplementedError


def get_provider(config):
    """
    Factory: return an instantiated provider adapter for `config`.
    Lazily imports implementations so missing SDKs don't break startup.
    """
    code = config.provider_code

    if code == 'FAKE':
        from .fake import FakeProvider
        return FakeProvider(config)

    if code == 'MTN_MOMO':
        from .mtn import MTNProvider
        return MTNProvider(config)

    if code == 'AIRTEL_MONEY':
        from .airtel import AirtelProvider
        return AirtelProvider(config)

    if code == 'CELLULANT':
        from .cellulant import CellulantProvider
        return CellulantProvider(config)

    raise ValueError(f'Unknown provider code: {code}')
''')

# ═════════════════════════════════════════════
# providers/fake.py
# ═════════════════════════════════════════════
add(PROV / "fake.py", r'''"""
Fake provider for local testing.

Simulates MTN/Airtel behavior without any real API:
- collect() returns CONFIRMED immediately (in sandbox).
- disburse() returns COMPLETED immediately (in sandbox).
- Webhook signature check accepts any request with header `X-Fake-Secret`
  matching the config's `webhook_secret`.
"""
import hashlib
import hmac
from decimal import Decimal
from secrets import token_hex

from .base import BaseMomoProvider


class FakeProvider(BaseMomoProvider):
    code = 'FAKE'
    name = 'Fake Provider'

    def collect(self, reference, amount, phone, description=''):
        txn_id = f'FAKE-{token_hex(6).upper()}'
        return {
            'provider_txn_id': txn_id,
            'status': 'CONFIRMED',
            'raw': {
                'simulated': True,
                'reference': reference,
                'amount': str(amount),
                'phone': phone,
                'description': description,
            },
        }

    def disburse(self, reference, amount, phone, description=''):
        txn_id = f'FAKE-{token_hex(6).upper()}'
        return {
            'provider_txn_id': txn_id,
            'status': 'COMPLETED',
            'raw': {
                'simulated': True,
                'reference': reference,
                'amount': str(amount),
                'phone': phone,
                'description': description,
            },
        }

    def verify_webhook(self, headers, body_bytes):
        secret = (self.config.webhook_secret or '').encode()
        if not secret:
            return True  # dev mode: accept all
        sig = headers.get('X-Fake-Secret', '')
        expected = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse_webhook(self, payload):
        return {
            'provider_txn_id': payload.get('provider_txn_id', ''),
            'status': payload.get('status', 'FAILED'),
            'amount': Decimal(str(payload.get('amount', 0))) if payload.get('amount') else None,
            'phone': payload.get('phone'),
            'error': payload.get('error', ''),
        }

    def get_balance(self):
        return {
            'currency': 'ZMW',
            'available': Decimal('1000000.00'),
            'raw': {'simulated': True},
        }
''')

# ═════════════════════════════════════════════
# services.py
# ═════════════════════════════════════════════
add(APP / "services.py", r'''"""
Mobile money services — create intents, process webhooks, confirm payments.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    MomoProviderConfig, PaymentIntent, DisbursementIntent,
)
from .providers.base import get_provider, MomoProviderError

logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================
def _generate_reference(org, prefix):
    today = timezone.now().strftime('%Y%m%d')
    base = f'{prefix}-{org.code.upper()}-{today}'
    from .models import PaymentIntent as PI, DisbursementIntent as DI
    Model = PI if prefix == 'MOMO' else DI
    last = Model.objects.filter(
        organization=org, reference__startswith=base,
    ).aggregate(m=Max('reference'))['m']
    seq = 1
    if last:
        try:
            seq = int(last.rsplit('-', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f'{base}-{seq:05d}'


def _get_config(org, provider_code):
    cfg = MomoProviderConfig.objects.filter(
        organization=org, provider_code=provider_code, is_active=True,
    ).first()
    if not cfg:
        raise ValueError(
            f'No active config for provider {provider_code}. '
            f'Configure it in Django admin first.'
        )
    return cfg


# ============================================================
# Inbound (Collections)
# ============================================================
class CollectionService:

    @staticmethod
    @transaction.atomic
    def initiate(org, client, amount, phone, provider_code,
                 loan=None, description='', user=None):
        """
        Create a PaymentIntent and call the provider to request payment.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive.')

        config = _get_config(org, provider_code)
        provider = get_provider(config)

        reference = _generate_reference(org, 'MOMO')

        intent = PaymentIntent.objects.create(
            organization=org,
            client=client,
            loan=loan,
            provider_code=provider_code,
            reference=reference,
            amount=amount,
            phone=phone,
            status='PENDING',
            expires_at=timezone.now() + timedelta(hours=24),
            raw_request={
                'amount': str(amount),
                'phone': phone,
                'description': description,
                'provider': provider_code,
            },
        )

        try:
            result = provider.collect(
                reference=reference,
                amount=amount,
                phone=phone,
                description=description,
            )
        except MomoProviderError as e:
            intent.status = 'FAILED'
            intent.error = str(e)
            intent.raw_response = e.raw
            intent.save()
            raise

        intent.provider_txn_id = result.get('provider_txn_id', '')
        intent.raw_response = result.get('raw', {})
        provider_status = result.get('status', 'PENDING')

        if provider_status == 'CONFIRMED':
            intent.status = 'CONFIRMED'
            intent.confirmed_at = timezone.now()
            intent.save()
            CollectionService._record_payment(intent, user)
        else:
            intent.status = 'PENDING'
            intent.save()

        return intent

    @staticmethod
    @transaction.atomic
    def process_webhook(provider_code, payload, headers, body_bytes, org=None):
        """
        Handle a provider callback: find the intent, mark it confirmed,
        and post the payment to the GL.
        """
        if org:
            configs = MomoProviderConfig.objects.filter(
                organization=org, provider_code=provider_code, is_active=True,
            )
        else:
            configs = MomoProviderConfig.objects.filter(
                provider_code=provider_code, is_active=True,
            )

        parsed = None
        intent = None

        for cfg in configs:
            provider = get_provider(cfg)
            try:
                if not provider.verify_webhook(headers, body_bytes):
                    continue
                parsed = provider.parse_webhook(payload)
                if parsed.get('provider_txn_id'):
                    intent = PaymentIntent.objects.filter(
                        provider_code=provider_code,
                        provider_txn_id=parsed['provider_txn_id'],
                        organization=cfg.organization,
                    ).first()
                if intent:
                    break
            except Exception as e:
                logger.warning(f'Webhook verify failed for {provider_code}: {e}')
                continue

        if not intent:
            logger.warning(
                f'No matching intent for webhook: {parsed}'
            )
            return None

        if intent.status in ('CONFIRMED', 'FAILED', 'CANCELLED'):
            # Idempotent — already handled
            return intent

        intent.raw_response = payload

        if parsed['status'] == 'CONFIRMED':
            intent.status = 'CONFIRMED'
            intent.confirmed_at = timezone.now()
            intent.save()
            CollectionService._record_payment(intent)
        else:
            intent.status = 'FAILED'
            intent.error = parsed.get('error', '')
            intent.save()

        return intent

    @staticmethod
    def _record_payment(intent, user=None):
        """Convert a confirmed intent into a Payment + post to GL."""
        if intent.payment_id:
            return intent.payment

        if not intent.loan:
            # Nothing to allocate — mark as unallocated for manual review
            logger.warning(f'Intent {intent.reference} has no loan — skipping payment.')
            return None

        from apps.payments.services_admin import record_payment

        # Use the intent's creator or fall back to client's branch manager
        actor = user or intent.loan.loan_officer or intent.loan.approved_by
        if not actor:
            logger.warning(f'No actor for intent {intent.reference} — skipping.')
            return None

        try:
            payment, _ = record_payment(
                loan=intent.loan,
                amount=intent.amount,
                user=actor,
                payment_method=intent.provider_code,
                transaction_ref=intent.provider_txn_id or intent.reference,
                notes=f'Auto-recorded via MoMo: {intent.reference}',
            )
            intent.payment = payment
            intent.save(update_fields=['payment'])
            return payment
        except Exception as e:
            logger.exception(f'Failed to record payment for intent {intent.reference}: {e}')
            intent.error = str(e)
            intent.save(update_fields=['error'])
            return None


# ============================================================
# Outbound (Disbursements)
# ============================================================
class DisbursementService:

    @staticmethod
    @transaction.atomic
    def initiate(org, client, amount, phone, provider_code,
                 loan=None, description='', user=None):
        """
        Send money to the client's mobile wallet.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive.')

        config = _get_config(org, provider_code)
        provider = get_provider(config)

        reference = _generate_reference(org, 'PAYOUT')

        intent = DisbursementIntent.objects.create(
            organization=org,
            client=client,
            loan=loan,
            provider_code=provider_code,
            reference=reference,
            amount=amount,
            phone=phone,
            status='PENDING',
            initiated_by=user,
            raw_request={
                'amount': str(amount),
                'phone': phone,
                'description': description,
                'provider': provider_code,
            },
        )

        try:
            result = provider.disburse(
                reference=reference,
                amount=amount,
                phone=phone,
                description=description,
            )
        except MomoProviderError as e:
            intent.status = 'FAILED'
            intent.error = str(e)
            intent.raw_response = e.raw
            intent.save()
            raise

        intent.provider_txn_id = result.get('provider_txn_id', '')
        intent.raw_response = result.get('raw', {})
        provider_status = result.get('status', 'PROCESSING')

        if provider_status == 'COMPLETED':
            intent.status = 'COMPLETED'
            intent.completed_at = timezone.now()
        elif provider_status == 'FAILED':
            intent.status = 'FAILED'
            intent.error = result.get('error', '')
        else:
            intent.status = 'PROCESSING'

        intent.save()
        return intent

    @staticmethod
    @transaction.atomic
    def process_webhook(provider_code, payload, headers, body_bytes, org=None):
        """Handle disbursement status update from provider."""
        if org:
            configs = MomoProviderConfig.objects.filter(
                organization=org, provider_code=provider_code, is_active=True,
            )
        else:
            configs = MomoProviderConfig.objects.filter(
                provider_code=provider_code, is_active=True,
            )

        parsed = None
        intent = None
        for cfg in configs:
            provider = get_provider(cfg)
            try:
                if not provider.verify_webhook(headers, body_bytes):
                    continue
                parsed = provider.parse_webhook(payload)
                if parsed.get('provider_txn_id'):
                    intent = DisbursementIntent.objects.filter(
                        provider_code=provider_code,
                        provider_txn_id=parsed['provider_txn_id'],
                        organization=cfg.organization,
                    ).first()
                if intent:
                    break
            except Exception:
                continue

        if not intent:
            return None

        if intent.status in ('COMPLETED', 'FAILED', 'CANCELLED'):
            return intent

        intent.raw_response = payload
        if parsed['status'] == 'CONFIRMED':
            intent.status = 'COMPLETED'
            intent.completed_at = timezone.now()
        else:
            intent.status = 'FAILED'
            intent.error = parsed.get('error', '')
        intent.save()
        return intent
''')

# ═════════════════════════════════════════════
# webhooks.py
# ═════════════════════════════════════════════
add(APP / "webhooks.py", r'''"""
Webhook receivers for mobile money providers.
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services import CollectionService, DisbursementService

logger = logging.getLogger(__name__)


def _extract_headers(request):
    return {k: v for k, v in request.headers.items()}


@csrf_exempt
@require_http_methods(['POST'])
def collection_webhook(request, provider_code):
    """
    POST /api/momo/webhook/collection/<provider_code>/

    Each provider posts their confirmation here. We verify, find the
    pending intent, and either confirm it (auto-record payment) or mark
    it failed.
    """
    provider_code = provider_code.upper()

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception as e:
        logger.warning(f'Bad webhook JSON for {provider_code}: {e}')
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    try:
        intent = CollectionService.process_webhook(
            provider_code=provider_code,
            payload=payload,
            headers=_extract_headers(request),
            body_bytes=request.body,
        )
    except Exception as e:
        logger.exception(f'Webhook processing failed: {e}')
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

    if not intent:
        return JsonResponse({'ok': False, 'error': 'no matching intent'}, status=404)

    return JsonResponse({
        'ok': True,
        'reference': intent.reference,
        'status': intent.status,
    })


@csrf_exempt
@require_http_methods(['POST'])
def disbursement_webhook(request, provider_code):
    """
    POST /api/momo/webhook/disbursement/<provider_code>/
    """
    provider_code = provider_code.upper()

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    try:
        intent = DisbursementService.process_webhook(
            provider_code=provider_code,
            payload=payload,
            headers=_extract_headers(request),
            body_bytes=request.body,
        )
    except Exception as e:
        logger.exception(f'Disbursement webhook failed: {e}')
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

    if not intent:
        return JsonResponse({'ok': False, 'error': 'no matching intent'}, status=404)

    return JsonResponse({
        'ok': True,
        'reference': intent.reference,
        'status': intent.status,
    })
''')

# ═════════════════════════════════════════════
# urls.py
# ═════════════════════════════════════════════
add(APP / "urls.py", r'''from django.urls import path
from . import webhooks

urlpatterns = [
    path(
        'webhook/collection/<str:provider_code>/',
        webhooks.collection_webhook,
        name='momo-collection-webhook',
    ),
    path(
        'webhook/disbursement/<str:provider_code>/',
        webhooks.disbursement_webhook,
        name='momo-disbursement-webhook',
    ),
]
''')

# ═════════════════════════════════════════════
# admin.py
# ═════════════════════════════════════════════
add(APP / "admin.py", r'''from django.contrib import admin
from .models import MomoProviderConfig, PaymentIntent, DisbursementIntent


@admin.register(MomoProviderConfig)
class MomoProviderConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'provider_code', 'is_active', 'is_sandbox', 'updated_at']
    list_filter = ['provider_code', 'is_active', 'is_sandbox']
    search_fields = ['organization__code', 'merchant_id', 'short_code']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'provider_code', 'amount', 'phone',
        'status', 'client', 'created_at',
    ]
    list_filter = ['provider_code', 'status', 'created_at']
    search_fields = ['reference', 'provider_txn_id', 'phone', 'client__first_name', 'client__last_name']
    readonly_fields = [
        'id', 'reference', 'provider_txn_id', 'raw_request', 'raw_response',
        'created_at', 'confirmed_at',
    ]
    autocomplete_fields = ['client', 'loan', 'payment']
    date_hierarchy = 'created_at'


@admin.register(DisbursementIntent)
class DisbursementIntentAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'provider_code', 'amount', 'phone',
        'status', 'client', 'created_at', 'completed_at',
    ]
    list_filter = ['provider_code', 'status', 'created_at']
    search_fields = ['reference', 'provider_txn_id', 'phone', 'client__first_name', 'client__last_name']
    readonly_fields = [
        'id', 'reference', 'provider_txn_id', 'raw_request', 'raw_response',
        'created_at', 'completed_at',
    ]
    autocomplete_fields = ['client', 'loan']
    date_hierarchy = 'created_at'
''')

# ═════════════════════════════════════════════
# Write
# ═════════════════════════════════════════════
def main():
    print("Installing Phase AK — Mobile Money Integration...")
    for path, content in FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        print(f"  + {rel}")
    print(f"\nDone. {len(FILES)} files written.")


if __name__ == "__main__":
    main()