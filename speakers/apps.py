from django.apps import AppConfig


class SpeakersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "speakers"
    verbose_name = "Speaker portal"

    def ready(self):
        import speakers.receivers  # noqa: F401  registers the signal receivers
        from common.send_emails import register_credential_pattern

        # The invitation link signs its reader in as the presenter. It is
        # withheld from the sent-email record by shape, not only when the
        # sender names it, so no stale worker or forgetful caller can store
        # one. Pinned to the real URL by tests/common/test_email_records.py.
        register_credential_pattern(
            r"https?://[^\s<>()\[\]]+/speakers/invitations/[^\s<>()\[\]]+"
        )
