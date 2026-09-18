"""Small factory functions for speakers models.

No factory library is installed in this portal, so these are plain functions
with sensible defaults; pass keyword arguments to override any field.
"""

from datetime import datetime, timedelta, timezone

from speakers.models import (
    DiscordChannel,
    Invitation,
    Presenter,
    PresenterRole,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)
from speakers.program_types import presenter_role, session_type

_counter = {"n": 0}


def _next():
    _counter["n"] += 1
    return _counter["n"]


def make_settings(conference, **kwargs):
    kwargs.setdefault("speaker_module_enabled", True)
    return SpeakerSettings.objects.create(conference=conference, **kwargs)


def make_session(conference, **kwargs):
    """``kind`` may be a SessionType or a code such as ``"PANEL"``; the
    defaults are seeded for the edition on first use."""
    n = _next()
    kind = kwargs.pop("kind", "WORKSHOP")
    if not isinstance(kind, SessionType):
        kind = session_type(conference, kind)
    kwargs.setdefault("title", f"Session {n}")
    return Session.objects.create(conference=conference, kind=kind, **kwargs)


def make_presenter(conference, **kwargs):
    n = _next()
    kwargs.setdefault("display_name", f"Presenter {n}")
    kwargs.setdefault("email", f"presenter{n}@example.com")
    return Presenter.objects.create(conference=conference, **kwargs)


def add_presenter(session, presenter, confirmed=False, **kwargs):
    """``role`` may be a PresenterRole or a code; defaults to the type's
    default role."""
    role = kwargs.pop("role", None)
    if role is None:
        role = session.kind.default_role
    elif not isinstance(role, PresenterRole):
        role = presenter_role(session.conference, role)
    kwargs["role"] = role
    if confirmed:
        kwargs.setdefault("confirmed_at", datetime.now(tz=timezone.utc))
    return SessionPresenter.objects.create(
        session=session, presenter=presenter, **kwargs
    )


def make_channel(conference, **kwargs):
    n = _next()
    kwargs.setdefault("name", f"channel-{n}")
    return DiscordChannel.objects.create(conference=conference, **kwargs)


def make_slot(session, **kwargs):
    kwargs.setdefault(
        "start_utc", datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc) + timedelta()
    )
    return ScheduleSlot.objects.create(session=session, **kwargs)


def make_invitation(presenter, session=None, **kwargs):
    return Invitation.objects.create(presenter=presenter, session=session, **kwargs)
