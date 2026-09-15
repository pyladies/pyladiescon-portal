"""Encrypted-at-rest text field for secrets such as API tokens.

Backed by ``cryptography.Fernet`` with the key from ``settings.FERNET_KEY``
(the ``FERNET_KEY`` environment variable; derived from ``SECRET_KEY`` only in
DEBUG and under pytest, see ``portal/settings.py``). Storing a secret in a
plain field is never the fallback: with no key configured the field refuses
to save.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def _fernet():
    key = getattr(settings, "FERNET_KEY", None)
    if not key:
        raise ImproperlyConfigured(
            "FERNET_KEY is not set; it is required to store encrypted fields."
        )
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """A TextField whose database value is a Fernet token."""

    description = "Text, encrypted at rest"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ImproperlyConfigured(
                "Stored value cannot be decrypted with the configured FERNET_KEY."
            ) from exc
