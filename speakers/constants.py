"""Enumerations for the speaker portal (design document §8).

Session types and presenter roles are not here: they are rows
(``SessionType``, ``PresenterRole``) seeded per edition by
``speakers.program_types`` so organizers can add to them.
"""

from django.db import models


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


class ChannelKind(models.TextChoices):
    STAGE = "STAGE", "Stage"
    VOICE = "VOICE", "Voice"
    TEXT = "TEXT", "Text"
    FORUM = "FORUM", "Forum"
