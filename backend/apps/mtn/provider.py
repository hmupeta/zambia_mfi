# apps/mtn/providers.py
"""
MTN Mobile Money provider adapter.
"""
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import uuid
import base64
from decimal import Decimal

from apps.momo.providers.base import BaseMomoProvider, MomoProviderError

logger = logging.getLogger(__name__)


class MtnProvider(BaseMomoProvider):
    code = 'MTN_MOMO'
    name = 'MTN Mobile Money'

    PROD_BASE    = 'https://proxy.momoapi.mtn.com'
    SANDBOX_BASE = 'https://sandbox.momodeveloper.mtn.com'

    @property
    def API_BASE(self):
        return self.SANDBOX_BASE if self.TARGET_ENV == 'sandbox' else self.PROD_BASE

    @property
    def TARGET_ENV(self):
        return 'sandbox' if getattr(self.config, 'is_sandbox', False) else 'mtnzambia'

    # --------------------------------------------------------
    # Credentials
    # --------------------------------------------------------
    def _credentials(self):
        subscription_key = (self.config.plain_credential('subscription_key') or '').strip()
        api_user = (self.config.merchant_id or '').strip()
        api_key = (self.config.plain_credential('api_key') or '').strip()
        if not subscription_key or not api_user or not api_key:
            raise MomoProviderError(
                'MTN requires subscription_key, merchant_id (API user UUID), '
                'and api_key (API secret).'
            )
        return subscription_key, api_user, api_key

    def _access_token(self):
        """Get OAuth2 bearer token from MTN (dynamically uses Collection or Disbursement endpoint)."""
        subscription_key, api_user, api_key = self._credentials()
        
        if getattr(self.config, 'transaction_type', 'COLLECTION') == 'DISBURSEMENT':
            url = f'{self.API_BASE}/disbursement/token/'
        else:
            url = f'{self.API_BASE}/collection/token/'

        creds = f'{api_user}:{api_key}'
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

        msisdn = (phone or '').replace('+', '').replace(' ', '')
        if msisdn.startswith('0'):
            msisdn = '260' + msisdn[1:]

        mtn_ref_id = str(uuid.uuid4())

        payload = {
            'amount': str(amount),
            'currency': 'EUR' if self.config.is_sandbox else 'ZMW',
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
        req.add_header('X-Reference-Id', mtn_ref_id)
        req.add_header('X-Target-Environment', self.TARGET_ENV)
        req.add_header('Ocp-Apim-Subscription-Key', subscription_key)
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return {
                    'provider_txn_id': mtn_ref_id,
                    'status': 'PENDING',
                    'raw': {'status_code': resp.status, 'reference': mtn_ref_id},
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            print(f"❌ MTN COLLECT HTTP {e.code}: {body}")
            logger.warning(f'MTN collect HTTP {e.code}: {body}')
            raise MomoProviderError(f'MTN collect failed: {e.code}', raw={'body': body})
        except Exception as e:
            raise MomoProviderError(f'MTN collect failed: {e}')

    # --------------------------------------------------------
    # Disbursements (FIXED)
    # --------------------------------------------------------
    def disburse(self, reference, amount, phone, description=''):
        subscription_key, _, _ = self._credentials()
        token = self._access_token()
        url = f'{self.API_BASE}/disbursement/v1_0/transfer'

        # Format phone
        msisdn = (phone or '').replace('+', '').replace(' ', '')
        if msisdn.startswith('0'):
            msisdn = '260' + msisdn[1:]

        # MTN REQUIRES A UUID FOR X-REFERENCE-ID
        mtn_ref_id = str(uuid.uuid4())

        payload = {
            'amount': str(amount),
            'currency': 'EUR' if self.config.is_sandbox else 'ZMW',
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
        req.add_header('X-Reference-Id', mtn_ref_id)  # <--- NOW A UUID
        req.add_header('X-Target-Environment', self.TARGET_ENV)
        req.add_header('Ocp-Apim-Subscription-Key', subscription_key)
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return {
                    'provider_txn_id': mtn_ref_id,
                    'status': 'PROCESSING',
                    'raw': {'status_code': resp.status, 'reference': mtn_ref_id},
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            # --- SHOW THE EXACT MTN ERROR ---
            print(f"\n❌❌❌ MTN DISBURSE HTTP {e.code} ❌❌❌")
            print(f"❌ PAYLOAD SENT: {json.dumps(payload, indent=2)}")
            print(f"❌ MTN RESPONSE: {body}\n")
            raise MomoProviderError(f'MTN disburse failed: {e.code}', raw={'body': body})
        except Exception as e:
            raise MomoProviderError(f'MTN disburse failed: {e}')

    # --------------------------------------------------------
    # Webhook
    # --------------------------------------------------------
    def verify_webhook(self, headers, body_bytes):
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

    def test_connection(self):
        try:
            token = self._access_token()
        except MomoProviderError as e:
            return {'ok': False, 'message': str(e)}

        if not token:
            return {'ok': False, 'message': 'MTN returned an empty token.'}

        return {
            'ok': True,
            'message': (
                f'Authenticated successfully against '
                f'{self.TARGET_ENV}. Token length: {len(token)} chars.'
            ),
        }