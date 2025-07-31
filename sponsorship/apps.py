from django.apps import AppConfig


class SponsorshipConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sponsorship"

    def ready(self):
        import sponsorship.signals  # noqa: this registers the signals
