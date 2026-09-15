"""Small factory functions for speakers models.

No factory library is installed in this portal, so these are plain functions
with sensible defaults; pass keyword arguments to override any field.
"""

from datetime import datetime, timedelta, timezone

from speakers.constants import PresenterRole, SessionKind
from speakers.models import (
    DiscordChannel,
    Presenter,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SpeakerSettings,
)

_counter = {"n": 0}


def _next():
    _counter["n"] += 1
    return _counter["n"]


def make_settings(conference, **kwargs):
    kwargs.setdefault("speaker_module_enabled", True)
    return SpeakerSettings.objects.create(conference=conference, **kwargs)


def make_session(conference, **kwargs):
    n = _next()
    kwargs.setdefault("kind", SessionKind.WORKSHOP)
    kwargs.setdefault("title", f"Session {n}")
    return Session.objects.create(conference=conference, **kwargs)


def make_presenter(conference, **kwargs):
    n = _next()
    kwargs.setdefault("display_name", f"Presenter {n}")
    kwargs.setdefault("email", f"presenter{n}@example.com")
    return Presenter.objects.create(conference=conference, **kwargs)


def add_presenter(session, presenter, confirmed=False, **kwargs):
    kwargs.setdefault("role", PresenterRole.PRESENTER)
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
