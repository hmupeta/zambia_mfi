"""SMTP email adapter."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailResult:
    def __init__(self, success, message_id='', error=''):
        self.success = success
        self.message_id = message_id
        self.error = error


def send_email(to_address, subject, body, config):
    if not to_address or '@' not in to_address:
        return EmailResult(False, error='Invalid email: ' + str(to_address))
    if not config.email_host:
        return EmailResult(False, error='SMTP host not configured.')
    if not config.email_from_address:
        return EmailResult(False, error='From address not configured.')

    from_name = (config.email_from_name or '').strip()
    from_addr = config.email_from_address
    from_header = (from_name + ' <' + from_addr + '>') if from_name else from_addr

    msg = EmailMessage()
    msg['Subject'] = subject or 'Notification'
    msg['From'] = from_header
    msg['To'] = to_address
    msg.set_content(body or '')
    msg.add_alternative('<pre style="font-family: inherit;">' + (body or '') + '</pre>', subtype='html')

    try:
        if config.email_use_tls:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(config.email_host, config.email_port, timeout=15) as smtp:
                smtp.starttls(context=ctx)
                if config.email_username:
                    smtp.login(config.email_username, config.email_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(config.email_host, config.email_port, timeout=15) as smtp:
                if config.email_username:
                    smtp.login(config.email_username, config.email_password)
                smtp.send_message(msg)
        return EmailResult(True, message_id=msg['Message-ID'] or '')
    except Exception as e:
        logger.warning("Email failed to %s: %s", to_address, e)
        return EmailResult(False, error=str(e))
