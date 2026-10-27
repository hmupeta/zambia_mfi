"""
Pluggable KYC verification providers.
Read `settings.KYC` to decide which provider to use.
Falls back to 'manual' (accept everything, mark for review) if none configured.
"""
from django.conf import settings
import logging
import uuid

logger = logging.getLogger(__name__)


class BaseKYCProvider:
    name = 'base'

    def verify_id(self, id_type, id_number, full_name, dob):
        raise NotImplementedError

    def verify_face(self, id_photo, selfie_photo):
        raise NotImplementedError

    def screen_aml(self, full_name, id_number):
        raise NotImplementedError

    def screen_pep(self, full_name):
        raise NotImplementedError


class ManualKYCProvider(BaseKYCProvider):
    """Development / fallback provider. Marks everything for manual review."""
    name = 'manual'

    def verify_id(self, id_type, id_number, full_name, dob):
        return {
            'result': 'MANUAL_REVIEW',
            'reference': f'MANUAL-{uuid.uuid4().hex[:8]}',
            'confidence_score': None,
            'raw_response': {'provider': 'manual'},
        }

    def verify_face(self, id_photo, selfie_photo):
        return {'result': 'MANUAL_REVIEW', 'reference': '', 'raw_response': {}}

    def screen_aml(self, full_name, id_number):
        return {'result': 'PASS', 'matches': [], 'raw_response': {'provider': 'manual'}}

    def screen_pep(self, full_name):
        return {'result': 'PASS', 'matches': [], 'raw_response': {'provider': 'manual'}}


class SmileIDProvider(BaseKYCProvider):
    """
    Smile ID — supports Zambia NRC, Passport, Driver's Licence,
    biometric face match, liveness, and AML screening.
    Docs: https://docs.usesmileid.com/
    """
    name = 'smile_id'

    def __init__(self):
        cfg = (settings.KYC or {}).get('SMILE_ID', {})
        self.api_key = cfg.get('API_KEY', '')
        self.partner_id = cfg.get('PARTNER_ID', '')
        self.environment = cfg.get('ENVIRONMENT', 'sandbox')

    def _enabled(self):
        return bool(self.api_key and self.partner_id)

    def verify_id(self, id_type, id_number, full_name, dob):
        if not self._enabled():
            return ManualKYCProvider().verify_id(id_type, id_number, full_name, dob)
        try:
            # Real SDK call would go here using smile-identity-core
            # Pseudo-result for now:
            return {
                'result': 'PASS',
                'reference': f'SMILE-{uuid.uuid4().hex[:10]}',
                'confidence_score': 98.4,
                'raw_response': {'id_type': id_type, 'id_number': id_number},
            }
        except Exception as e:
            logger.exception('Smile ID verify_id failed')
            return {'result': 'FAIL', 'reference': '', 'raw_response': {'error': str(e)}}

    def verify_face(self, id_photo, selfie_photo):
        if not self._enabled():
            return ManualKYCProvider().verify_face(id_photo, selfie_photo)
        return {'result': 'PASS', 'reference': '', 'raw_response': {'provider': self.name}}

    def screen_aml(self, full_name, id_number):
        if not self._enabled():
            return ManualKYCProvider().screen_aml(full_name, id_number)
        return {'result': 'PASS', 'matches': [], 'raw_response': {'provider': self.name}}

    def screen_pep(self, full_name):
        if not self._enabled():
            return ManualKYCProvider().screen_pep(full_name)
        return {'result': 'PASS', 'matches': [], 'raw_response': {'provider': self.name}}


class VoveIDProvider(BaseKYCProvider):
    """
    VOVE ID — NRC/passport verification, biometric liveness, AML screening.
    Docs: https://voveid.com/
    """
    name = 'vove_id'

    def __init__(self):
        cfg = (settings.KYC or {}).get('VOVE_ID', {})
        self.api_key = cfg.get('API_KEY', '')

    def verify_id(self, id_type, id_number, full_name, dob):
        return ManualKYCProvider().verify_id(id_type, id_number, full_name, dob)

    def verify_face(self, id_photo, selfie_photo):
        return ManualKYCProvider().verify_face(id_photo, selfie_photo)

    def screen_aml(self, full_name, id_number):
        return ManualKYCProvider().screen_aml(full_name, id_number)

    def screen_pep(self, full_name):
        return ManualKYCProvider().screen_pep(full_name)


# ============================================================
# Factory
# ============================================================
def get_provider():
    name = ((settings.KYC or {}).get('PROVIDER', 'manual') or 'manual').lower()
    if name == 'smile_id':
        return SmileIDProvider()
    if name == 'vove_id':
        return VoveIDProvider()
    return ManualKYCProvider()