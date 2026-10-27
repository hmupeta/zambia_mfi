"""Africa's Talking SMS adapter."""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

AT_LIVE = 'https://api.africastalking.com/version1/messaging'
AT_SANDBOX = 'https://api.sandbox.africastalking.com/version1/messaging'


class SMSResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def _summarize_http_error(code, body):
    """
    Turn AT's HTTP error into a human-readable string.
    AT returns JSON like {"SMSMessageData":{"Message":"Invalid API Key"}}
    or sometimes plain text. Include a short hint for the common cases.
    """
    body = (body or '').strip()
    hint = ''
    if code == 401:
        hint = ' (check: sandbox username must be "sandbox"; API key must match the same environment)'
    elif code == 403:
        hint = ' (check: destination number may not be registered in the sandbox)'
    elif code == 400:
        hint = ' (check: sender ID / shortcode may not be approved for this account)'

    if body:
        # Try to extract AT's own message string from the JSON envelope
        try:
            parsed = json.loads(body)
            msg = (
                parsed.get('SMSMessageData', {}).get('Message')
                or parsed.get('error')
                or parsed.get('message')
            )
            if msg:
                return f'AT {code}: {msg}{hint}'
        except (ValueError, TypeError):
            pass
        # Not JSON, or no recognizable message — truncate raw body
        return f'AT {code}: {body[:300]}{hint}'

    return f'AT {code}: no response body{hint}'


def send_sms(to_number, message, config):
    username = (config.sms_username or '').strip()
    api_key = (config.sms_api_key or '').strip()
    sender_id = (config.sms_sender_id or '').strip()

    if not username or not api_key:
        return SMSResult(False, error="Africa's Talking credentials not configured.")

    url = AT_SANDBOX if config.is_sandbox else AT_LIVE

    payload = {'username': username, 'to': to_number, 'message': message}
    if sender_id:
        payload['from'] = sender_id

    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('apiKey', api_key)
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            parsed = json.loads(resp.read().decode('utf-8'))
            recipients = parsed.get('SMSMessageData', {}).get('Recipients', [])
            if recipients:
                r = recipients[0]
                if r.get('status', '').lower() == 'success':
                    return SMSResult(True, message_id=r.get('messageId', ''))
                return SMSResult(False, error=r.get('status', 'Unknown'))
            # No recipients — surface AT's top-level message if present
            top_msg = parsed.get('SMSMessageData', {}).get('Message', '')
            return SMSResult(
                False,
                error=f'No recipients in response. {top_msg}'.strip(),
            )

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        logger.warning(
            "AT SMS HTTP %s to %s — username=%r sandbox=%s — body=%s",
            e.code, to_number, username, config.is_sandbox, body[:500],
        )
        return SMSResult(False, error=_summarize_http_error(e.code, body))

    except urllib.error.URLError as e:
        # DNS failure, connection refused, TLS error, etc.
        logger.warning("AT SMS network error to %s: %s", to_number, e.reason)
        return SMSResult(False, error=f'Network error: {e.reason}')

    except Exception as e:
        logger.exception("AT SMS unexpected failure to %s", to_number)
        return SMSResult(False, error=f'{type(e).__name__}: {e}')