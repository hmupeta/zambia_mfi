# apps/momo/apps.py

from django.apps import AppConfig


class MomoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.momo'

    # Registry of provider code -> provider class.
    # Every provider in PROVIDER_CHOICES must appear here.
    MOMO_PROVIDERS = {}

    def ready(self):
        # Imported here to avoid circular imports at module load
        from apps.momo.providers.fake import FakeProvider
        from apps.mtn.provider import MtnProvider
        # from apps.airtel.provider import AirtelProvider
        # from apps.zamtel.provider import ZamtelProvider

        self.MOMO_PROVIDERS.update({
            'FAKE':         FakeProvider,
            'MTN_MOMO':     MtnProvider,          # ← ADD THIS LINE
            # 'AIRTEL_MONEY': AirtelProvider,     # ← uncomment when ready
            # 'ZAMTEL':       ZamtelProvider,     # ← uncomment when ready
        })