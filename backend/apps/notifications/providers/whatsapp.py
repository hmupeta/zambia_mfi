"""Twilio WhatsApp adapter."""
import base64
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class WhatsAppResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def send_whatsapp(to_number, message, config):
    account_sid = (config.twilio_account_sid or '').strip()
    auth_token = (config.twilio_auth_token or '').strip()
    from_number = (config.whatsapp_from or '').strip()

    if not account_sid or not auth_token:
        return WhatsAppResult(False, error='Twilio credentials not configured.')
    if not from_number:
        return WhatsAppResult(False, error='WhatsApp From number not configured.')

    if not from_number.startswith('whatsapp:'):
        from_number = 'whatsapp:' + from_number
    to_whatsapp = to_number if to_number.startswith('whatsapp:') else 'whatsapp:' + to_number

    url = 'https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json' % account_sid
    payload = {'From': from_number, 'To': to_whatsapp, 'Body': message}
    data = urllib.parse.urlencode(payload).encode('utf-8')

    creds = base64.b64encode(('%s:%s' % (account_sid, auth_token)).encode()).decode()

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', 'Basic ' + creds)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            parsed = json.loads(resp.read().decode('utf-8'))
            sid = parsed.get('sid', '')
            if sid:
                return WhatsAppResult(True, message_id=sid)
            return WhatsAppResult(False, error='Unexpected: %s' % parsed.get('status'))
    except Exception as e:
        logger.warning("WhatsApp failed to %s: %s", to_number, e)
        return WhatsAppResult(False, error=str(e))
