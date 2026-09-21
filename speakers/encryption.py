"""Encrypted-at-rest text field for secrets such as API tokens.

Backed by ``cryptography.Fernet``. Keys come from ``settings.FERNET_KEYS``
(comma-separated, first key encrypts, every key decrypts, so a key can be
rolled without downtime) or the single ``settings.FERNET_KEY``; both are
read from the environment variables of the same names, and the single key
is derived from ``SECRET_KEY`` only in DEBUG and under pytest (see
``portal/settings.py``). Storing a secret in a plain field is never the
fallback: with no key configured the field refuses to save.

Reading is forgiving on purpose: a row that cannot be decrypted (the key
is missing on this deploy, or was rotated away) loads as an
``Undecryptable`` value rather than raising, because ``SpeakerSettings``
is loaded whole by every path that reads any edition setting and a missing
env var must not take the checklists, the digests or the admin down with
the pretix integration. Callers treat ``Undecryptable`` as "not
configured"; it is logged once per process, and saving it back is refused.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

logger = logging.getLogger(__name__)

_warned = False


class Undecryptable:
    """A stored token this deploy cannot decrypt. Falsy, so ``if value``
    reads as "not configured"; keeps the token so nothing is lost."""

    def __init__(self, token):
        self.token = token

    def __bool__(self):
        return False

    def __str__(self):
        return ""

    def __repr__(self):
        return "Undecryptable(<token>)"


def usable(value):
    """True when ``value`` is a real, decrypted, non-empty secret."""
    return isinstance(value, str) and bool(value)


def _keys():
    keys = getattr(settings, "FERNET_KEYS", None) or ""
    keys = [k.strip() for k in keys.split(",") if k.strip()]
    single = getattr(settings, "FERNET_KEY", None)
    if single and single not in keys:
        keys.append(single)
    return keys


def _fernet():
    keys = _keys()
    if not keys:
        raise ImproperlyConfigured(
            "FERNET_KEY (or FERNET_KEYS) is not set; it is required to store "
            "encrypted fields."
        )
    return MultiFernet([Fernet(k) for k in keys])


def _warn_once(reason):
    global _warned
    if not _warned:
        logger.error("Encrypted field cannot be read: %s", reason)
        _warned = True


class EncryptedTextField(models.TextField):
    """A TextField whose database value is a Fernet token."""

    description = "Text, encrypted at rest"

    def get_prep_value(self, value):
        if isinstance(value, Undecryptable):
            raise ImproperlyConfigured(
                "Refusing to save a value this deploy could not decrypt; set the "
                "right FERNET_KEY (or FERNET_KEYS) first."
            )
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except ImproperlyConfigured as exc:
            _warn_once(str(exc))
            return Undecryptable(value)
        except InvalidToken:
            _warn_once("stored value does not match FERNET_KEY / FERNET_KEYS")
            return Undecryptable(value)
