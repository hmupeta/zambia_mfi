"""
Broadpay (Lenco) provider adapter.

Lenco exposes a clean REST API for mobile money collections and transfers.

Docs: https://lenco.co/docs
"""
import json
import logging
import urllib.request
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class BroadpayProvider(BaseMomoProvider):
    code = 'BROADPAY'
    name = 'Broadpay (Lenco)'

    API_BASE = 'https://api.lenco.co/access/v2'

    def _bearer(self):
        api_key = (self.config.api_key or '').strip()
        if not api_key:
            raise MomoProviderError('Lenco bearer token not configured.')
        return api_key

    def _detect_operator(self, phone):
        """Best-effort operator detection by prefix."""
        p = (phone or '').replace('+', '').replace(' ', '')
        # Zambian prefixes: 096/076 = MTN, 097/077 = Airtel, 095/075 = Zamtel
        p = p[-9:] if len(p) >= 9 else p
        if p.startswith(('096', '076')):
            return 'mtn'
        if p.startswith(('097', '077')):
            return 'airtel'
        if p.startswith(('095', '075')):
            return 'zamtel'
        return 'mtn'  # fallback

    def collect(self, reference, amount, phone, description=''):
        token = self._bearer()
        url = f'{self.API_BASE}/collections/mobile-money'

        payload = {
            'operator': self._detect_operator(phone),
            'phone': phone,
            'amount': str(amount),
            'currency': 'ZMW',
            'reference': reference,
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Lenco collect failed: {e}')
            raise MomoProviderError(f'Lenco API request failed: {e}')

        inner = parsed.get('data', parsed)
        return {
            'provider_txn_id': inner.get('id', '') or inner.get('reference', ''),
            'status': 'PENDING',
            'raw': parsed,
        }

    def disburse(self, reference, amount, phone, description=''):
        token = self._bearer()
        url = f'{self.API_BASE}/transfers/mobile-money'

        payload = {
            'amount': str(amount),
            'currency': 'ZMW',
            'reference': reference,
            'phone': phone,
            'operator': self._detect_operator(phone),
            'country': 'ZM',
            'description': description or '',
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Lenco disburse failed: {e}')
            raise MomoProviderError(f'Lenco transfer failed: {e}')

        inner = parsed.get('data', parsed)
        return {
            'provider_txn_id': inner.get('id', '') or inner.get('reference', ''),
            'status': 'PROCESSING',
            'raw': parsed,
        }

    def verify_webhook(self, headers, body_bytes):
        # Lenco signs webhooks with HMAC-SHA256 in the 'X-Lenco-Signature' header.
        # Enable strict verification once you have a webhook secret configured.
        secret = (self.config.webhook_secret or '').encode()
        if not secret:
            return True  # dev mode
        import hmac, hashlib
        sig = headers.get('X-Lenco-Signature', '')
        expected = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse_webhook(self, payload):
        status = (payload.get('status') or '').lower()
        inner = payload.get('data', payload)
        return {
            'provider_txn_id': inner.get('id', ''),
            'status': 'CONFIRMED' if status in ('successful', 'success', 'completed') else 'FAILED',
            'amount': Decimal(str(inner.get('amount', 0))) if inner.get('amount') else None,
            'phone': inner.get('mobileMoneyDetails', {}).get('phone'),
            'error': inner.get('reasonForFailure', ''),
        }

    def get_balance(self):
        raise NotImplementedError
