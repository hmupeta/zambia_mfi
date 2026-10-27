from django.apps import AppConfig


class AirtelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.airtel'
    label = 'airtel'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import AirtelProvider
        self.MOMO_PROVIDERS = {'AIRTEL_MONEY': AirtelProvider}
