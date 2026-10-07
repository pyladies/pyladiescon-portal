"""The public program (design §11.5, task 6.1).

Every public surface (the calendar feeds now; the JSON API, the widget,
the embed and the exports later) reads through ``public_program`` and
``public_presenters``, so the three switches are evaluated in one place:

- the edition's master switch, ``SpeakerSettings.program_visibility``;
- the session: on the published schedule, and either published by an
  organizer (``is_public``) or a program item (breaks, opening, closing),
  which goes public with the schedule itself;
- the presenter: public only through such a session, and only if they have
  not opted out (their name still shows on their sessions).

A preview token, handed to the website build, bypasses the first two
switches until it is regenerated or the program goes public.
"""

import secrets

from django.core import signing
from django.db.models import Q

from .constants import ProgramVisibility, SessionStatus
from .models import Presenter, Session, SpeakerSettings

PREVIEW_SALT = "speakers.program-preview"


def _settings(conference):
    return SpeakerSettings.objects.filter(conference=conference).first()


def program_is_published(conference):
    """Whether the master switch is on for ``conference``."""
    settings = _settings(conference)
    return (
        settings is not None
        and settings.program_visibility == ProgramVisibility.PUBLISHED
    )


def preview_token(settings):
    """The current preview link token, minting the key on first use."""
    if not settings.preview_key:
        settings.preview_key = secrets.token_urlsafe(16)
        settings.save(update_fields=["preview_key"])
    return signing.dumps(
        {"c": settings.conference_id, "k": settings.preview_key}, salt=PREVIEW_SALT
    )


def regenerate_preview(settings):
    """Revoke every preview link handed out so far; returns the new token."""
    settings.preview_key = secrets.token_urlsafe(16)
    settings.save(update_fields=["preview_key"])
    return preview_token(settings)


def preview_is_valid(conference, token):
    """A token for this edition, of the current generation, while the
    program is still internal. No time limit: the link works until it is
    regenerated or the program goes public."""
    if not token:
        return False
    try:
        data = signing.loads(token, salt=PREVIEW_SALT)
    except signing.BadSignature:
        return False
    settings = _settings(conference)
    return bool(
        settings is not None
        and settings.preview_key
        and settings.program_visibility == ProgramVisibility.INTERNAL
        and data == {"c": conference.pk, "k": settings.preview_key}
    )


def public_program(conference, preview=None):
    """The sessions the public may see, as a queryset.

    Empty while the program is internal, unless ``preview`` is a valid
    token, which shows every session on the published schedule whether or
    not an organizer has published it yet.
    """
    previewing = preview_is_valid(conference, preview)
    if not previewing and not program_is_published(conference):
        return Session.objects.none()
    sessions = (
        Session.objects.for_conference(conference)
        .filter(published_slot__isnull=False)
        .exclude(status=SessionStatus.CANCELLED)
    )
    if not previewing:
        sessions = sessions.filter(Q(is_public=True) | Q(kind__is_content=False))
    return sessions


def public_presenters(conference, preview=None):
    """Presenters with a public profile: confirmed on a session of the
    public program, and not opted out. Anyone else is absent, never a
    placeholder."""
    return (
        Presenter.objects.filter(
            conference=conference,
            is_public=True,
            session_presenters__session__in=public_program(conference, preview),
            session_presenters__confirmed_at__isnull=False,
        )
        .distinct()
        .order_by("display_name")
    )
