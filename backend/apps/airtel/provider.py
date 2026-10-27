"""
Airtel Money provider adapter.

Airtel Africa Developer portal provides standard mobile money APIs
for collections and disbursements across 14 African countries,
including Zambia.

Docs: https://developers.airtel.africa
"""
import base64
import json
import logging
import urllib.request
import urllib.parse
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class AirtelProvider(BaseMomoProvider):
    code = 'AIRTEL_MONEY'
    name = 'Airtel Money'

    # Zambia endpoint
    API_BASE = 'https://openapi.airtel.africa'
    COUNTRY = 'ZM'
    CURRENCY = 'ZMW'

    def _credentials(self):
        client_id = (self.config.api_key or '').strip()
        client_secret = (self.config.api_secret or '').strip()
        if not client_id or not client_secret:
            raise MomoProviderError(
                'Airtel requires api_key (client_id) and api_secret (client_secret).'
            )
        return client_id, client_secret

    def _auth_token(self):
        """Get OAuth2 bearer token from Airtel."""
        client_id, client_secret = self._credentials()
        url = f'{self.API_BASE}/auth/oauth2/token'

        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
        }
        data = urllib.parse.urlencode(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
                return parsed.get('access_token', '')
        except Exception as e:
            logger.warning(f'Airtel auth failed: {e}')
            raise MomoProviderError(f'Airtel OAuth failed: {e}')

    def collect(self, reference, amount, phone, description=''):
        token = self._auth_token()
        url = f'{self.API_BASE}/merchant/v2/payments/'

        payload = {
            'reference': reference,
            'subscriber': {
                'country': self.COUNTRY,
                'currency': self.CURRENCY,
                'msisdn': phone,
            },
            'transaction': {
                'amount': float(amount),
                'country': self.COUNTRY,
                'currency': self.CURRENCY,
                'id': reference,
            },
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('X-Country', self.COUNTRY)
        req.add_header('X-Currency', self.CURRENCY)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Airtel collect failed: {e}')
            raise MomoProviderError(f'Airtel API request failed: {e}')

        inner = parsed.get('data', {}).get('transaction', {})
        return {
            'provider_txn_id': inner.get('id', '') or inner.get('airtel_money_id', ''),
            'status': 'PENDING',
            'raw': parsed,
        }

    def disburse(self, reference, amount, phone, description=''):
        token = self._auth_token()
        url = f'{self.API_BASE}/standard/v1/disbursements/'

        payload = {
            'payee': {
                'msisdn': phone,
                'currency': self.CURRENCY,
                'country': self.COUNTRY,
            },
            'reference': reference,
            'transaction': {
                'amount': float(amount),
                'country': self.COUNTRY,
                'currency': self.CURRENCY,
                'id': reference,
            },
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('X-Country', self.COUNTRY)
        req.add_header('X-Currency', self.CURRENCY)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Airtel disburse failed: {e}')
            raise MomoProviderError(f'Airtel API request failed: {e}')

        inner = parsed.get('data', {}).get('transaction', {})
        return {
            'provider_txn_id': inner.get('id', '') or inner.get('airtel_money_id', ''),
            'status': 'PROCESSING',
            'raw': parsed,
        }

    def verify_webhook(self, headers, body_bytes):
        secret = (self.config.webhook_secret or '').encode()
        if not secret:
            return True
        import hmac, hashlib
        sig = headers.get('X-Airtel-Signature', '')
        expected = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def parse_webhook(self, payload):
        inner = payload.get('transaction', payload)
        status = (inner.get('status') or payload.get('status') or '').lower()
        return {
            'provider_txn_id': inner.get('id', '') or inner.get('airtel_money_id', ''),
            'status': 'CONFIRMED' if status in ('ts', 'success', 'successful') else 'FAILED',
            'amount': Decimal(str(inner.get('amount', 0))) if inner.get('amount') else None,
            'phone': inner.get('msisdn'),
            'error': payload.get('error_description', ''),
        }

    def get_balance(self):
        raise NotImplementedError
