# apps/core/crypto.py

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    """
    Build a Fernet instance from MOMO_ENCRYPTION_KEY (preferred) or SECRET_KEY.

    Fernet requires a 32-byte url-safe base64 key. We derive one
    deterministically from whatever secret we have available.
    """
    raw_key = getattr(settings, 'MOMO_ENCRYPTION_KEY', '') or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns '' for empty input."""
    if not value:
        return ''
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """
    Decrypt an encrypted string. Returns '' on failure (e.g. legacy plaintext
    rows or a rotated key).
    """
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ''