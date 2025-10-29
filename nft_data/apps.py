from django.apps import AppConfig
from django.conf import settings

class NftDataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'nft_data'

    def ready(self):
        import nft_data.signals
