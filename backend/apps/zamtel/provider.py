"""
Zamtel Money provider adapter.

Zamtel operates its own mobile money service (formerly Zamtel Kwacha).
API access requires a merchant agreement with Zamtel.

Contact: Zamtel Business / Enterprise Sales
"""
import json
import logging
import urllib.request
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class ZamtelProvider(BaseMomoProvider):
    code = 'ZAMTEL'
    name = 'Zamtel Money'

    def _credentials(self):
        api_key = (self.config.api_key or '').strip()
        merchant_id = (self.config.merchant_id or '').strip()
        base_url = (self.config.callback_url or '').strip()
        if not api_key or not merchant_id or not base_url:
            raise MomoProviderError(
                'Zamtel requires api_key, merchant_id, and callback_url (base URL).'
            )
        return api_key, merchant_id, base_url.rstrip('/')

    def collect(self, reference, amount, phone, description=''):
        api_key, merchant_id, base_url = self._credentials()
        url = f'{base_url}/collections'

        payload = {
            'merchant_id': merchant_id,
            'reference': reference,
            'amount': str(amount),
            'msisdn': phone,
            'currency': 'ZMW',
            'description': description or 'MFI Loan Payment',
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {api_key}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Zamtel collect failed: {e}')
            raise MomoProviderError(f'Zamtel API request failed: {e}')

        return {
            'provider_txn_id': parsed.get('transactionId', '') or parsed.get('id', ''),
            'status': 'PENDING',
            'raw': parsed,
        }

    def disburse(self, reference, amount, phone, description=''):
        api_key, merchant_id, base_url = self._credentials()
        url = f'{base_url}/disbursements'

        payload = {
            'merchant_id': merchant_id,
            'reference': reference,
            'amount': str(amount),
            'msisdn': phone,
            'currency': 'ZMW',
            'description': description or '',
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {api_key}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Zamtel disburse failed: {e}')
            raise MomoProviderError(f'Zamtel API request failed: {e}')

        return {
            'provider_txn_id': parsed.get('transactionId', '') or parsed.get('id', ''),
            'status': 'PROCESSING',
            'raw': parsed,
        }

    def verify_webhook(self, headers, body_bytes):
        secret = (self.config.webhook_secret or '').encode()
        if not secret:
            return True
        import hmac, hashlib
        sig = headers.get('X-Zamtel-Signature', '')
        expected = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse_webhook(self, payload):
        status = (payload.get('status') or '').lower()
        return {
            'provider_txn_id': payload.get('transactionId', '') or payload.get('id', ''),
            'status': 'CONFIRMED' if status in ('success', 'successful', 'completed') else 'FAILED',
            'amount': Decimal(str(payload.get('amount', 0))) if payload.get('amount') else None,
            'phone': payload.get('msisdn'),
            'error': payload.get('errorMessage', ''),
        }

    def get_balance(self):
        raise NotImplementedError
