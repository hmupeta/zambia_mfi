"""
Provider abstraction for sending SMS / WhatsApp messages.

Selected via settings.NOTIFICATIONS['PROVIDER']:
    - 'console'         → logs to stdout, marks as SENT (dev)
    - 'africastalking'  → real SMS via Africa's Talking
    - 'whatsapp_cloud'  → Meta WhatsApp Cloud API

Each provider implements:
    send(phone, body, channel) -> dict with keys:
        provider, provider_message_id, provider_response, status, error_message
"""
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class BaseProvider:
    name = 'base'

    def send(self, phone, body, channel='SMS'):
        raise NotImplementedError


class ConsoleProvider(BaseProvider):
    """
    Development provider — logs the message and returns success without any
    external API call. Use this in dev/CI.
    """
    name = 'console'

    def send(self, phone, body, channel='SMS'):
        logger.info(
            "\n" + "=" * 60 +
            f"\n[{channel}] To: {phone}\n{body}\n" + "=" * 60
        )
        return {
            'provider': self.name,
            'provider_message_id': f'console-{timezone.now().timestamp()}',
            'provider_response': {'provider': 'console', 'status': 'logged'},
            'status': 'SENT',
            'error_message': '',
        }


class AfricasTalkingSMSProvider(BaseProvider):
    """
    Africa's Talking SMS. Requires:
        AT_USERNAME, AT_API_KEY, AT_SENDER_ID
    """
    name = 'africastalking'

    def __init__(self):
        cfg = settings.NOTIFICATIONS.get('AFRICASTALKING', {})
        self.username = cfg.get('USERNAME')
        self.api_key = cfg.get('API_KEY')
        self.sender_id = cfg.get('SENDER_ID', '')

    def send(self, phone, body, channel='SMS'):
        if not self.username or not self.api_key:
            return {
                'provider': self.name,
                'provider_message_id': '',
                'provider_response': None,
                'status': 'FAILED',
                'error_message': "Africa's Talking credentials not configured.",
            }

        try:
            import africastalking
            africastalking.initialize(self.username, self.api_key)
            sms = africastalking.SMS

            kwargs = {'message': body, 'recipients': [phone]}
            if self.sender_id:
                kwargs['sender_id'] = self.sender_id

            response = sms.send(**kwargs)
            # Response shape: {'SMSMessageData': {'Recipients': [...]}}
            recipients = response.get('SMSMessageData', {}).get('Recipients', [])
            first = recipients[0] if recipients else {}
            status = first.get('status', '')

            return {
                'provider': self.name,
                'provider_message_id': first.get('messageId', ''),
                'provider_response': response,
                'status': 'SENT' if status.lower() in ('success', 'sent') else 'FAILED',
                'error_message': '' if status.lower() in ('success', 'sent') else status,
            }
        except Exception as e:
            logger.exception("Africa's Talking send failed")
            return {
                'provider': self.name,
                'provider_message_id': '',
                'provider_response': None,
                'status': 'FAILED',
                'error_message': str(e),
            }


class WhatsAppCloudProvider(BaseProvider):
    """
    Meta WhatsApp Cloud API. Requires:
        WA_PHONE_ID, WA_ACCESS_TOKEN
    """
    name = 'whatsapp_cloud'

    def __init__(self):
        cfg = settings.NOTIFICATIONS.get('WHATSAPP', {})
        self.phone_id = cfg.get('PHONE_ID')
        self.access_token = cfg.get('ACCESS_TOKEN')
        self.api_url = f"https://graph.facebook.com/v20.0/{self.phone_id}/messages"

    def send(self, phone, body, channel='WHATSAPP'):
        if not self.phone_id or not self.access_token:
            return {
                'provider': self.name,
                'provider_message_id': '',
                'provider_response': None,
                'status': 'FAILED',
                'error_message': 'WhatsApp Cloud credentials not configured.',
            }

        try:
            import requests
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
            }
            # Strip leading + from phone for WA API
            to = phone.lstrip('+')
            payload = {
                'messaging_product': 'whatsapp',
                'to': to,
                'type': 'text',
                'text': {'preview_url': False, 'body': body},
            }
            r = requests.post(self.api_url, json=payload, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()

            message_id = ''
            msgs = data.get('messages', [])
            if msgs:
                message_id = msgs[0].get('id', '')

            return {
                'provider': self.name,
                'provider_message_id': message_id,
                'provider_response': data,
                'status': 'SENT',
                'error_message': '',
            }
        except Exception as e:
            logger.exception('WhatsApp Cloud send failed')
            return {
                'provider': self.name,
                'provider_message_id': '',
                'provider_response': None,
                'status': 'FAILED',
                'error_message': str(e),
            }


# ============================================================
# Factory
# ============================================================
def get_provider():
    name = (settings.NOTIFICATIONS or {}).get('PROVIDER', 'console').lower()

    if name == 'africastalking':
        return AfricasTalkingSMSProvider()
    if name == 'whatsapp_cloud':
        return WhatsAppCloudProvider()
    return ConsoleProvider()