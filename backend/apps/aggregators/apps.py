from django.apps import AppConfig


class AggregatorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.aggregators'
    label = 'aggregators'

    # Populated in ready() — the momo engine reads this registry
    MOMO_PROVIDERS = {}

    def ready(self):
        from .kazang import KazangProvider
        from .izwe import IZweProvider
        from .broadpay import BroadpayProvider
        from .zynle import ZynleProvider

        self.MOMO_PROVIDERS = {
            'KAZANG':   KazangProvider,
            'IZWE':     IZweProvider,
            'BROADPAY': BroadpayProvider,
            'ZYNLE':    ZynleProvider,
        }
