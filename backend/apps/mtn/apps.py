from django.apps import AppConfig


class MtnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mtn'
    label = 'mtn'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import MtnProvider
        self.MOMO_PROVIDERS = {'MTN_MOMO': MtnProvider}
