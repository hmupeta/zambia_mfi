# apps/portal/auth.py
"""
Lightweight client portal authentication.

Uses Django's password hashers directly (no User model involved).
Session-based: after login, `request.session['portal_client_id']` is set.
"""
from datetime import timedelta
from functools import wraps

from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import redirect
from django.utils import timezone

from apps.clients.models import Client
from .models import ClientPortalAccount


LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


# ============================================================
# Setup
# ============================================================
def set_password(account, raw_password):
    """Hash and store a new password."""
    account.password = make_password(raw_password)
    account.save(update_fields=['password', 'updated_at'])


def create_account_for_client(client, raw_password):
    """Create or reset a portal account for a client."""
    account, created = ClientPortalAccount.objects.get_or_create(client=client)
    set_password(account, raw_password)
    account.is_active = True
    account.failed_attempts = 0
    account.locked_until = None
    account.save(update_fields=['is_active', 'failed_attempts', 'locked_until', 'updated_at'])
    return account


# ============================================================
# Login
# ============================================================
def authenticate_portal(phone, raw_password):
    """
    Returns (client, account, error_message).
    On success: (client, account, None)
    On failure: (None, None, reason)
    """
    phone = (phone or '').strip()
    if not phone or not raw_password:
        return None, None, 'Phone and password are required.'

    try:
        client = Client.objects.filter(phone=phone, is_active=True).first()
        if not client:
            return None, None, 'Invalid credentials.'

        account = ClientPortalAccount.objects.filter(client=client).first()
        if not account:
            return None, None, 'No portal account. Contact your branch.'

        if not account.is_active:
            return None, None, 'Account is disabled.'

        # Lockout check
        if account.locked_until and account.locked_until > timezone.now():
            mins = int((account.locked_until - timezone.now()).total_seconds() / 60) + 1
            return None, None, f'Account locked. Try again in {mins} minutes.'

        # Verify password
        if not check_password(raw_password, account.password):
            account.failed_attempts += 1
            if account.failed_attempts >= LOCKOUT_THRESHOLD:
                account.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
                account.failed_attempts = 0
            account.save(update_fields=['failed_attempts', 'locked_until', 'updated_at'])
            return None, None, 'Invalid credentials.'

        # Success
        account.failed_attempts = 0
        account.locked_until = None
        account.last_login = timezone.now()
        account.save(update_fields=['failed_attempts', 'locked_until', 'last_login', 'updated_at'])
        return client, account, None

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f'Portal auth error: {e}')
        return None, None, 'Login failed. Please try again.'


# ============================================================
# Session helpers
# ============================================================
def log_in(request, client):
    request.session['portal_client_id'] = str(client.id)
    request.session.set_expiry(60 * 60 * 12)  # 12 hours


def log_out(request):
    request.session.pop('portal_client_id', None)
    request.session.flush()


def get_current_client(request):
    """Return the logged-in Client or None."""
    client_id = request.session.get('portal_client_id')
    if not client_id:
        return None
    try:
        return Client.objects.get(id=client_id, is_active=True)
    except Client.DoesNotExist:
        return None


# ============================================================
# Decorator for portal views
# ============================================================
def portal_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        client = get_current_client(request)
        if client is None:
            return redirect(f'/portal/login/?next={request.path}')
        request.portal_client = client
        return view_func(request, *args, **kwargs)
    return _wrapped