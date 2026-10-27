#!/usr/bin/env python3
"""Create apps/mtn/ — dedicated MTN MoMo adapter.
Run from backend/:   python install_mtn_app.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
APP = ROOT / "apps" / "mtn"

FILES = []

def add(path, content):
    FILES.append((path, content))


add(APP / "__init__.py", "")

add(APP / "apps.py", r'''from django.apps import AppConfig


class MtnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mtn'
    label = 'mtn'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import MtnProvider
        self.MOMO_PROVIDERS = {'MTN_MOMO': MtnProvider}
''')

add(APP / "provider.py", r'''"""
MTN Mobile Money provider adapter.

MTN MoMo Open API for Zambia. Uses OAuth2 client credentials,
then a collections/disbursements API per transaction.

Docs: https://momodeveloper.mtn.com
Region: Zambia
Currency: ZMW
"""
import json
import logging
import urllib.request
import urllib.parse
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class MtnProvider(BaseMomoProvider):
    code = 'MTN_MOMO'
    name = 'MTN Mobile Money'

    API_BASE = 'https://proxy.momoapi.mtn.com'
    TARGET_ENV = 'mtnzambia'   # or 'sandbox'

    # --------------------------------------------------------
    # Credentials
    # --------------------------------------------------------
    def _credentials(self):
        subscription_key = (self.config.subscription_key or '').strip()
        api_user = (self.config.merchant_id or '').strip()
        api_key = (self.config.api_key or '').strip()
        if not subscription_key or not api_user or not api_key:
            raise MomoProviderError(
                'MTN requires subscription_key, merchant_id (API user UUID), '
                'and api_key (API secret).'
            )
        return subscription_key, api_user, api_key

    def _access_token(self):
        """Get OAuth2 bearer token from MTN."""
        subscription_key, api_user, api_key = self._credentials()
        url = f'{self.API_BASE}/collection/token/'

        creds = f'{api_user}:{api_key}'
        import base64
        auth = base64.b64encode(creds.encode()).decode()

        req = urllib.request.Request(url, method='POST')
        req.add_header('Authorization', f'Basic {auth}')
        req.add_header('Ocp-Apim-Subscription-Key', subscription_key)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = json.loads(resp.read().decode('utf-8'))
                return parsed.get('access_token', '')
        except Exception as e:
            logger.warning(f'MTN auth failed: {e}')
            raise MomoProviderError(f'MTN OAuth failed: {e}')

    # --------------------------------------------------------
    # Collections
    # --------------------------------------------------------
    def collect(self, reference, amount, phone, description=''):
        subscription_key, _, _ = self._credentials()
        token = self._access_token()
        url = f'{self.API_BASE}/collection/v1_0/requesttopay'

        # Normalize phone to international format without '+'
        msisdn = (phone or '').replace('+', '').replace(' ', '')

        payload = {
            'amount': str(amount),
            'currency': 'ZMW',
            'externalId': reference,
            'payer': {
                'partyIdType': 'MSISDN',
                'partyId': msisdn,
            },
            'payerMessage': description or 'MFI Loan Payment',
            'payeeNote': description or 'MFI Loan Payment',
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('X-Reference-Id', reference)
        req.add_header('X-Target-Environment', self.TARGET_ENV)
        req.add_header('Ocp-Apim-Subscription-Key', subscription_key)
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                # MTN returns 202 Accepted with no body — the reference IS the txn id
                return {
                    'provider_txn_id': reference,
                    'status': 'PENDING',
                    'raw': {'status_code': resp.status, 'reference': reference},
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            logger.warning(f'MTN collect HTTP {e.code}: {body}')
            raise MomoProviderError(f'MTN collect failed: {e.code}', raw={'body': body})
        except Exception as e:
            raise MomoProviderError(f'MTN collect failed: {e}')

    # --------------------------------------------------------
    # Disbursements
    # --------------------------------------------------------
    def disburse(self, reference, amount, phone, description=''):
        subscription_key, _, _ = self._credentials()
        token = self._access_token()
        url = f'{self.API_BASE}/disbursement/v1_0/transfer'

        msisdn = (phone or '').replace('+', '').replace(' ', '')

        payload = {
            'amount': str(amount),
            'currency': 'ZMW',
            'externalId': reference,
            'payee': {
                'partyIdType': 'MSISDN',
                'partyId': msisdn,
            },
            'payerMessage': description or 'Loan Disbursement',
            'payeeNote': description or 'Loan Disbursement',
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('X-Reference-Id', reference)
        req.add_header('X-Target-Environment', self.TARGET_ENV)
        req.add_header('Ocp-Apim-Subscription-Key', subscription_key)
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return {
                    'provider_txn_id': reference,
                    'status': 'PROCESSING',
                    'raw': {'status_code': resp.status, 'reference': reference},
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            raise MomoProviderError(f'MTN disburse failed: {e.code}', raw={'body': body})

    # --------------------------------------------------------
    # Webhook
    # --------------------------------------------------------
    def verify_webhook(self, headers, body_bytes):
        # MTN posts callbacks with no signature by default.
        # Verify by comparing the X-Reference-Id to a known pending intent.
        return True

    def parse_webhook(self, payload):
        status = (payload.get('status') or '').upper()
        return {
            'provider_txn_id': payload.get('externalId') or payload.get('referenceId'),
            'status': 'CONFIRMED' if status == 'SUCCESSFUL' else 'FAILED',
            'amount': Decimal(str(payload.get('amount', 0))) if payload.get('amount') else None,
            'phone': payload.get('payer', {}).get('partyId'),
            'error': payload.get('reason', ''),
        }

    def get_balance(self):
        raise NotImplementedError
''')


def main():
    print("Installing apps/mtn/...")
    for path, content in FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  + {path.relative_to(ROOT)}")
    print(f"\nDone. {len(FILES)} files written.")


if __name__ == "__main__":
    main()