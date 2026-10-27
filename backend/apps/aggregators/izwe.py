"""
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
