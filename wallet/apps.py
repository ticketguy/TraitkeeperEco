from django.apps import AppConfig


class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'

    def ready(self):
        """
        Import signals when the app is ready.
        This ensures signal handlers are registered.
        """
        import wallet.signals  # noqa
