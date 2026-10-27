# apps/momo/providers/base.py
"""
Abstract mobile money provider adapter.

Each provider (MTN, Airtel, Zamtel, Kazang, etc.) implements this interface.
Services call these methods; they never touch provider-specific code.

Provider resolution:
    get_provider(config) walks every installed AppConfig and looks for a
    MOMO_PROVIDERS dict mapping provider codes to provider classes. Add a
    new provider by installing a new app — no changes to this file needed.
"""
from abc import ABC, abstractmethod


class MomoProviderError(Exception):
    """Raised when a provider call fails."""
    def __init__(self, message, code='', raw=None):
        super().__init__(message)
        self.code = code
        self.raw = raw or {}


class BaseMomoProvider(ABC):
    """
    Interface every provider adapter must implement.
    All methods return a dict with a consistent shape.
    """

    code = 'BASE'
    name = 'Base Provider'

    def __init__(self, config):
        """`config` is a MomoProviderConfig instance."""
        self.config = config

    # ----------------------------------------------------------
    # Inbound collections
    # ----------------------------------------------------------
    @abstractmethod
    def collect(self, reference, amount, phone, description=''):
        """
        Request a payment FROM the client.

        Returns:
            {
                'provider_txn_id': str,
                'status': str,              # PENDING | CONFIRMED | FAILED
                'redirect_url': str,        # optional
                'raw': dict,
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Outbound disbursements
    # ----------------------------------------------------------
    @abstractmethod
    def disburse(self, reference, amount, phone, description=''):
        """
        Send money TO the client's wallet.

        Returns:
            {
                'provider_txn_id': str,
                'status': str,              # PROCESSING | COMPLETED | FAILED
                'raw': dict,
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Webhook verification
    # ----------------------------------------------------------
    @abstractmethod
    def verify_webhook(self, headers, body_bytes):
        """Return True if the webhook signature is valid."""
        raise NotImplementedError

    # ----------------------------------------------------------
    # Webhook parsing
    # ----------------------------------------------------------
    @abstractmethod
    def parse_webhook(self, payload):
        """
        Normalize a provider webhook into a consistent shape.

        Returns:
            {
                'provider_txn_id': str,
                'status': str,              # CONFIRMED | FAILED
                'amount': Decimal | None,
                'phone': str | None,
                'error': str,
            }
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Optional / shared methods (not abstract — providers may override)
    # ----------------------------------------------------------
    def get_balance(self):
        """Optional: fetch merchant float balance."""
        raise NotImplementedError

    def test_connection(self):
        """
        Return {'ok': True, 'message': '...'} on success, or
        {'ok': False, 'message': '...'} on failure.
        Called from the settings UI 'Test connection' button.
        Providers that don't override this will fail cleanly.
        """
        raise NotImplementedError(
            f'{self.name} does not implement test_connection().'
        )


# ============================================================
# Provider factory
# ============================================================
def get_provider(config):
    """
    Return an instantiated provider adapter for `config`.

    Resolution order:
      1. Built-in providers that ship with the momo engine (FAKE).
      2. Any installed app whose AppConfig declares MOMO_PROVIDERS — a
         dict mapping provider code -> provider class.
    """
    from django.apps import apps as django_apps

    code = config.provider_code

    # Built-in: the fake provider ships with the engine
    if code == 'FAKE':
        from .fake import FakeProvider
        return FakeProvider(config)

    # External: check every installed app's registry
    for app_config in django_apps.get_app_configs():
        registry = getattr(app_config, 'MOMO_PROVIDERS', None)
        if registry and code in registry:
            return registry[code](config)

    raise ValueError(
        f'Unknown provider code: {code}. '
        f'Install the provider app or register it in AppConfig.MOMO_PROVIDERS.'
    )