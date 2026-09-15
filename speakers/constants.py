"""Enumerations for the speaker portal (design document §8)."""

from django.db import models


class SessionKind(models.TextChoices):
    """What a schedule row is. Content kinds carry presenters; program kinds
    are the skeleton of a day (opening, breaks, socials)."""

    WORKSHOP = "WORKSHOP", "Workshop"
    PANEL = "PANEL", "Panel"
    PYJAM = "PYJAM", "PyJam performance"
    TALK = "TALK", "Talk"
    LIGHTNING = "LIGHTNING", "Lightning talk"
    OPENING = "OPENING", "Opening"
    CLOSING = "CLOSING", "Closing"
    KEYNOTE = "KEYNOTE", "Keynote"
    ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
    BREAK = "BREAK", "Break"
    SOCIAL = "SOCIAL", "Social"
    OTHER = "OTHER", "Other"


CONTENT_KINDS = frozenset(
    {
        SessionKind.WORKSHOP,
        SessionKind.PANEL,
        SessionKind.PYJAM,
        SessionKind.TALK,
        SessionKind.LIGHTNING,
    }
)

# Default length in minutes per kind. The design fixes workshop (90) and
# panel (60); the rest are editable defaults organizers can override per row.
DEFAULT_DURATION_MINUTES = {
    SessionKind.WORKSHOP: 90,
    SessionKind.PANEL: 60,
    SessionKind.PYJAM: 30,
    SessionKind.TALK: 30,
    SessionKind.LIGHTNING: 5,
    SessionKind.OPENING: 15,
    SessionKind.CLOSING: 15,
    SessionKind.KEYNOTE: 45,
    SessionKind.ANNOUNCEMENT: 5,
    SessionKind.BREAK: 15,
    SessionKind.SOCIAL: 60,
    SessionKind.OTHER: 30,
}


class Delivery(models.TextChoices):
    LIVE = "LIVE", "Live"
    PRE_RECORDED = "PRE_RECORDED", "Pre-recorded"


class SessionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    INVITED = "INVITED", "Invited"
    CONFIRMED = "CONFIRMED", "Confirmed"
    SCHEDULED = "SCHEDULED", "Scheduled"
    PUBLISHED = "PUBLISHED", "Published"
    CANCELLED = "CANCELLED", "Cancelled"


class SessionLevel(models.TextChoices):
    ALL = "ALL", "All levels"
    BEGINNER = "BEGINNER", "Beginner"
    INTERMEDIATE = "INTERMEDIATE", "Intermediate"
    ADVANCED = "ADVANCED", "Advanced"


class PremiereLocation(models.TextChoices):
    DISCORD = "DISCORD", "Watch party on Discord"
    YOUTUBE = "YOUTUBE", "YouTube Premiere"


class PresenterRole(models.TextChoices):
    PRESENTER = "PRESENTER", "Presenter"
    CO_PRESENTER = "CO_PRESENTER", "Co-presenter"
    PANELIST = "PANELIST", "Panelist"
    MODERATOR = "MODERATOR", "Moderator"
    HOST = "HOST", "Host"
    PERFORMER = "PERFORMER", "Performer"


class ChannelKind(models.TextChoices):
    STAGE = "STAGE", "Stage"
    VOICE = "VOICE", "Voice"
    TEXT = "TEXT", "Text"
    FORUM = "FORUM", "Forum"
