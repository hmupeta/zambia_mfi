"""
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
