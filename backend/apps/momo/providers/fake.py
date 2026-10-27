"""
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
