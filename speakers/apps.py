from django.apps import AppConfig


class SpeakersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "speakers"
    verbose_name = "Speaker portal"

    def ready(self):
        import speakers.receivers  # noqa: F401  registers the signal receivers
