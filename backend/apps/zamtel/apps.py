from django.apps import AppConfig


class ZamtelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.zamtel'
    label = 'zamtel'

    MOMO_PROVIDERS = {}

    def ready(self):
        from .provider import ZamtelProvider
        self.MOMO_PROVIDERS = {'ZAMTEL': ZamtelProvider}
