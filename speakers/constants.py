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


class MediaKind(models.TextChoices):
    """Files that move through post-production (design §8.8)."""

    RAW_VIDEO = "RAW_VIDEO", "Raw video (performer upload)"
    INTRO = "INTRO", "Intro (MC)"
    OUTRO = "OUTRO", "Outro (MC)"
    PROCESSED_VIDEO = "PROCESSED_VIDEO", "Processed video (final cut)"
    TRANSCRIPT = "TRANSCRIPT", "Transcript"
    TRANSLATION = "TRANSLATION", "Translation"
    TITLE_CARD = "TITLE_CARD", "Title card"
    THUMBNAIL = "THUMBNAIL", "Thumbnail"
    OTHER = "OTHER", "Other"


class ChecklistScope(models.TextChoices):
    PRESENTER = "PRESENTER", "Per presenter (keyed by kind and role)"
    SESSION = "SESSION", "Per session (keyed by kind and delivery)"


class ItemOwner(models.TextChoices):
    SPEAKER = "SPEAKER", "Speaker"
    ORGANIZER = "ORGANIZER", "Organizer"


class DueAnchor(models.TextChoices):
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED", "Days after the invitation is accepted"
    CONFERENCE_START = "CONFERENCE_START", "Days before the conference starts"
    SESSION_START = "SESSION_START", "Days before the session starts"


class AssigneeDefault(models.TextChoices):
    UNASSIGNED = "UNASSIGNED", "Unassigned"
    LIAISON = "LIAISON", "The presenter's liaison"


class AutoRule(models.TextChoices):
    """Names of the auto-completion rules (design §9.3). Templates reference
    names only; the callables live in the registry (task 2.3)."""

    BIO_AND_HEADSHOT = "bio_and_headshot", "Bio and headshot are filled in"
    HANDBOOK_READ = "handbook_read", "Speaker guide read (current version)"
    INVITATION_SENT = "invitation_sent", "Invitation sent"
    INVITATION_ACCEPTED = "invitation_accepted", "Invitation accepted"
    SESSION_SCHEDULED = "session_scheduled", "Session has a slot"
    PRETIX_REGISTERED = "pretix_registered", "Registered on pretix"
    ASSET_EXISTS = "asset_exists", "A ready asset of the required kind exists"
    VIDEO_LENGTH_OK = "video_length_ok", "Video length within the limit"
    YOUTUBE_PUBLISHED = "youtube_published", "YouTube URL and publish time set"


# The language marker on a template item meaning "the session's language".
SESSION_LANGUAGE = "session"


class ItemStatus(models.TextChoices):
    TODO = "TODO", "To do"
    DONE = "DONE", "Done"
    SKIPPED = "SKIPPED", "Skipped"
    BLOCKED = "BLOCKED", "Blocked"


OPEN_ITEM_STATUSES = frozenset({ItemStatus.TODO, ItemStatus.BLOCKED})
