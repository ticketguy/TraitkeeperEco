from django.apps import AppConfig


class LearnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'learn'

    def ready(self):
        import learn.models  # replace with your actual app name