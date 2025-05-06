from django.apps import AppConfig


class VolunteerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "volunteer"

    def ready(self):
        import volunteer.signals  # noqa: F401
