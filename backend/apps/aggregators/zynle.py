"""
Zynle Pay provider adapter.

Zynle Pay is a Zambian payment gateway supporting cards and mobile money.

Docs: Contact Zynle for API spec — requires API ID + Private Key.
"""
import json
import logging
import urllib.request
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class ZynleProvider(BaseMomoProvider):
    code = 'ZYNLE'
    name = 'Zynle Pay'

    API_BASE = 'https://api.zynlepay.com/api/v1'

    def _credentials(self):
        api_id = (self.config.api_key or '').strip()
        private_key = (self.config.api_secret or '').strip()
        if not api_id or not private_key:
            raise MomoProviderError(
                'Zynle requires api_key (API ID) and api_secret (Private Key).'
            )
        return api_id, private_key

    def _post(self, path, payload):
        api_id, private_key = self._credentials()
        url = f'{self.API_BASE}{path}'
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('X-API-ID', api_id)
        req.add_header('X-API-KEY', private_key)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Zynle API failed: {e}')
            raise MomoProviderError(f'Zynle API request failed: {e}')

    def collect(self, reference, amount, phone, description=''):
        parsed = self._post('/collection', {
            'amount': str(amount),
            'currency': 'ZMW',
            'reference': reference,
            'phone': phone,
            'description': description or '',
        })
        return {
            'provider_txn_id': parsed.get('transactionId', '') or parsed.get('id', ''),
            'status': 'PENDING',
            'raw': parsed,
        }

    def disburse(self, reference, amount, phone, description=''):
        parsed = self._post('/disbursement', {
            'amount': str(amount),
            'currency': 'ZMW',
            'reference': reference,
            'phone': phone,
            'description': description or '',
        })
        return {
            'provider_txn_id': parsed.get('transactionId', '') or parsed.get('id', ''),
            'status': 'PROCESSING',
            'raw': parsed,
        }

    def verify_webhook(self, headers, body_bytes):
        # Zynle signs webhooks — enable when you have their signature spec
        secret = (self.config.webhook_secret or '').encode()
        if not secret:
            return True
        import hmac, hashlib
        sig = headers.get('X-Zynle-Signature', '')
        expected = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse_webhook(self, payload):
        status = (payload.get('status') or '').lower()
        return {
            'provider_txn_id': payload.get('transactionId', '') or payload.get('id', ''),
            'status': 'CONFIRMED' if status in ('success', 'successful', 'completed') else 'FAILED',
            'amount': Decimal(str(payload.get('amount', 0))) if payload.get('amount') else None,
            'phone': payload.get('phone'),
            'error': payload.get('errorMessage', ''),
        }

    def get_balance(self):
        raise NotImplementedError
