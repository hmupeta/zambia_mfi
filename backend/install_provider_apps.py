#!/usr/bin/env python3
"""Installer for provider-specific apps (aggregators, zamtel, airtel).
Run from backend/:   python install_provider_apps.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
AGG = ROOT / "apps" / "aggregators"
ZAM = ROOT / "apps" / "zamtel"
AIR = ROOT / "apps" / "airtel"

FILES = []
def add(path, content):
    FILES.append((path, content))

# ═════════════════════════════════════════════
# AGGREGATORS app
# ═════════════════════════════════════════════
add(AGG / "apps.py", r'''from django.apps import AppConfig


class AggregatorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.aggregators'
    label = 'aggregators'

    # Populated in ready() — the momo engine reads this registry
    MOMO_PROVIDERS = {}

    def ready(self):
        from .kazang import KazangProvider
        from .izwe import IZweProvider
        from .broadpay import BroadpayProvider
        from .zynle import ZynleProvider

        self.MOMO_PROVIDERS = {
            'KAZANG':   KazangProvider,
            'IZWE':     IZweProvider,
            'BROADPAY': BroadpayProvider,
            'ZYNLE':    ZynleProvider,
        }
''')

add(AGG / "kazang.py", r'''"""
Kazang provider adapter.

Kazang is a redirect-based payment gateway. The `collect()` method
returns a `redirect_url` where the client completes payment. Kazang
then redirects back to our `success_url`.

Docs: https://www.kazang.com (contact for API spec)
"""
import logging
import urllib.parse
import urllib.request
import json
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class KazangProvider(BaseMomoProvider):
    code = 'KAZANG'
    name = 'Kazang'

    def _credentials(self):
        """Returns (api_key, base_url)."""
        api_key = (self.config.api_key or '').strip()
        base_url = (self.config.callback_url or '').strip()
        if not api_key or not base_url:
            raise MomoProviderError(
                'Kazang requires api_key and callback_url (used as base_url). '
                'Configure them in the provider config.'
            )
        return api_key, base_url.rstrip('/')

    # --------------------------------------------------------
    # Collections (redirect flow)
    # --------------------------------------------------------
    def collect(self, reference, amount, phone, description=''):
        api_key, base_url = self._credentials()
        url = f'{base_url}/CreateTransaction'

        # These URLs must be reachable from the client's browser
        success_url = f'https://your-app.zm/portal/loans/?momo_ref={reference}&status=success'
        cancel_url  = f'https://your-app.zm/portal/loans/?momo_ref={reference}&status=cancel'

        payload = {
            'amount': float(amount),
            'service_description': description or 'MFI Loan Payment',
            'client_reference': reference,
            'cancel_url': cancel_url,
            'success_url': success_url,
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('API_KEY', api_key)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'Kazang collect failed: {e}')
            raise MomoProviderError(f'Kazang API request failed: {e}')

        return {
            'provider_txn_id': parsed.get('ID') or parsed.get('id') or '',
            'status': 'PENDING',
            'redirect_url': parsed.get('url') or parsed.get('URL') or '',
            'raw': parsed,
        }

    def disburse(self, reference, amount, phone, description=''):
        raise NotImplementedError(
            'Kazang does not expose direct disbursement via API.'
        )

    def verify_webhook(self, headers, body_bytes):
        # Kazang returns data via the success_url redirect, not a webhook
        return True

    def parse_webhook(self, payload):
        return {
            'provider_txn_id': payload.get('kazang_ref', ''),
            'status': 'CONFIRMED' if payload.get('kazang_ref') else 'FAILED',
            'amount': None,
            'phone': payload.get('cell'),
            'error': '',
        }

    def get_balance(self):
        raise NotImplementedError
''')

add(AGG / "izwe.py", r'''"""
IZwe Pay provider adapter.

IZwe operates primarily through POS terminals and a merchant portal.
For API integration, contact their merchant support — the contract varies.

This adapter is a placeholder until you sign an agreement and receive
their API spec.
"""
from apps.momo.providers.base import BaseMomoProvider, MomoProviderError


class IZweProvider(BaseMomoProvider):
    code = 'IZWE'
    name = 'IZwe Pay'

    def _credentials(self):
        api_key = (self.config.api_key or '').strip()
        base_url = (self.config.callback_url or '').strip()
        if not api_key or not base_url:
            raise MomoProviderError(
                'IZwe API credentials not configured. '
                'Contact IZwe merchant support for an API contract.'
            )
        return api_key, base_url.rstrip('/')

    # All methods raise NotImplementedError until the API contract is signed
    def collect(self, reference, amount, phone, description=''):
        raise NotImplementedError(
            'IZwe API contract required. IZwe integration is normally via '
            'POS terminals — contact merchant support for API access.'
        )

    def disburse(self, reference, amount, phone, description=''):
        raise NotImplementedError('IZwe direct disbursement not available.')

    def verify_webhook(self, headers, body_bytes):
        return False

    def parse_webhook(self, payload):
        return {'provider_txn_id': '', 'status': 'FAILED', 'amount': None,
                'phone': None, 'error': 'Not implemented'}

    def get_balance(self):
        raise NotImplementedError
''')

add(AGG / "broadpay.py", r'''"""
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
''')

add(AGG / "zynle.py", r'''"""
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
''')

# ═════════════════════════════════════════════
# ZAMTEL app
# ═════════════════════════════════════════════
add(ZAM / "apps.py", r'''from django.apps import AppConfig


class ZamtelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.zamtel'
    label = 'zamtel'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import ZamtelProvider
        self.MOMO_PROVIDERS = {'ZAMTEL': ZamtelProvider}
''')

add(ZAM / "provider.py", r'''"""
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
''')

# ═════════════════════════════════════════════
# AIRTEL app
# ═════════════════════════════════════════════
add(AIR / "apps.py", r'''from django.apps import AppConfig


class AirtelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.airtel'
    label = 'airtel'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import AirtelProvider
        self.MOMO_PROVIDERS = {'AIRTEL_MONEY': AirtelProvider}
''')

add(AIR / "provider.py", r'''"""
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
''')

# ═════════════════════════════════════════════
# Write
# ═════════════════════════════════════════════
def main():
    print("Installing provider-specific apps...")
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