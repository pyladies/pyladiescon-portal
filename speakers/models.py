"""Models for the speaker portal.

Every row is scoped to a ``portal.Conference`` (the design document calls it a
``Project``): that is the portal's per-edition tenant, so PyLadiesCon 2027 is a
new Conference row with the same code. See ``speakers/README.md``.
"""

import secrets
import zoneinfo
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .constants import (
    CONTENT_KINDS,
    DEFAULT_DURATION_MINUTES,
    ChannelKind,
    Delivery,
    PremiereLocation,
    PresenterRole,
    SessionKind,
    SessionLevel,
    SessionStatus,
)


class TimestampedModel(models.Model):
    """Abstract base with the portal's ``creation_date``/``modified_date``.

    ``portal.models.BaseModel`` is concrete (multi-table inheritance), so
    every child model gets a reverse accessor on it named after the child
    (``basemodel.session``, ``basemodel.role``...). That forbids any
    BaseModel child from having a field called ``session``, ``presenter``,
    ``role`` or ``language``, all of which this app needs, and costs a join
    on every query. Speakers models therefore share the same two timestamp
    fields through this abstract base instead.
    """

    creation_date = models.DateTimeField(
        "creation_date", editable=False, auto_now_add=True
    )
    modified_date = models.DateTimeField("modified_date", editable=False, auto_now=True)

    class Meta:
        abstract = True


class TransitionError(ValidationError):
    """A session status change whose precondition is not met."""


@lru_cache(maxsize=1)
def _known_timezones():
    return zoneinfo.available_timezones()


def validate_timezone(value):
    """Accept only IANA zone names the running Python knows about."""
    if value not in _known_timezones():
        raise ValidationError(f"{value!r} is not a known IANA timezone.")


def _unique_slug(model, conference, base, exclude_pk=None):
    """Return ``base`` or ``base-2``, ``base-3``... unused within ``conference``."""
    base = slugify(base)[:80] or "item"
    candidate = base
    counter = 2
    queryset = model.objects.filter(conference=conference)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    while queryset.filter(slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


class SpeakerSettings(TimestampedModel):
    """Per-edition configuration for the speaker module.

    One row per Conference, created by an organizer (admin) when the edition
    starts using the speaker portal. Holds the feature flag now and, in later
    stages, the edition's program visibility, pretix and media settings.
    """

    conference = models.OneToOneField(
        "portal.Conference",
        on_delete=models.CASCADE,
        related_name="speaker_settings",
    )
    speaker_module_enabled = models.BooleanField(
        default=False,
        help_text="Turn the speaker portal on for this edition.",
    )
    default_premiere_location = models.CharField(
        max_length=16,
        choices=PremiereLocation.choices,
        default=PremiereLocation.DISCORD,
        help_text="Where pre-recorded sessions premiere unless a session says otherwise.",
    )

    class Meta:
        verbose_name = "speaker settings"
        verbose_name_plural = "speaker settings"

    def __str__(self):
        return f"Speaker settings ({self.conference})"


def speaker_module_enabled(conference):
    """Whether the speaker module is switched on for ``conference``.

    False when there is no conference, no settings row, or the flag is off, so
    a freshly created edition is off until an organizer opts in.
    """
    if conference is None:
        return False
    return SpeakerSettings.objects.filter(
        conference=conference, speaker_module_enabled=True
    ).exists()


class ActivityLog(TimestampedModel):
    """What happened to a speaker-portal record, by whom (or automatically).

    ``actor`` is null for things the portal did on its own ("pretix order
    paid, registration marked done"). ``target`` is any speakers model.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="speaker_activity",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="speaker_activity",
    )
    action = models.CharField(max_length=64)
    message = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-creation_date", "-id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        who = self.actor.username if self.actor else "portal"
        return f"{who}: {self.action}"

    @classmethod
    def record(cls, conference, action, *, target=None, actor=None, message="", **data):
        """Write one entry. ``actor=None`` marks an automatic event."""
        entry = cls(
            conference=conference,
            action=action,
            actor=actor,
            message=message,
            data=data,
        )
        if target is not None:
            entry.target = target
        entry.save()
        return entry

    @classmethod
    def for_target(cls, target):
        """Entries about one record, newest first."""
        return cls.objects.filter(
            content_type=ContentType.objects.get_for_model(target),
            object_id=target.pk,
        ).select_related("actor")


class DiscordChannel(TimestampedModel):
    """A Discord channel the schedule can place sessions in.

    Channels are created on Discord by hand and recorded here (design §8.5).
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="discord_channels",
    )
    name = models.CharField(max_length=100)
    channel_id = models.CharField(
        max_length=32, blank=True, help_text="The numeric Discord channel id."
    )
    url = models.URLField(blank=True)
    kind = models.CharField(
        max_length=8, choices=ChannelKind.choices, default=ChannelKind.STAGE
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "name"], name="speakers_channel_name_per_edition"
            )
        ]

    def __str__(self):
        return self.name


class Presenter(TimestampedModel):
    """A person, independent of any session (design §8.2).

    ``user`` is linked when the invitation is accepted; a presenter can be
    added, scheduled and listed before they ever log in.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="presenters",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presenter_profiles",
    )
    liaison = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="liaison_for_presenters",
        help_text="The organizer or volunteer looking after this presenter.",
    )
    display_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, blank=True)
    email = models.EmailField(help_text="Invitation and reminder target.")
    pronouns = models.CharField(max_length=50, blank=True)
    bio_md = models.TextField("bio", blank=True, help_text="Markdown.")
    headshot = models.ImageField(upload_to="speakers/headshots/", blank=True)
    location = models.CharField(max_length=200, blank=True)
    timezone = models.CharField(
        max_length=64, default="UTC", validators=[validate_timezone]
    )
    website_url = models.URLField(blank=True)
    github_username = models.CharField(max_length=39, blank=True)
    mastodon_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    bluesky_username = models.CharField(max_length=100, blank=True)
    is_public = models.BooleanField(
        default=True,
        help_text="Off hides the bio, headshot and links on the public site; "
        "the name still appears on their sessions.",
    )

    class Meta:
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "email"],
                name="speakers_presenter_email_per_edition",
            ),
            models.UniqueConstraint(
                fields=["conference", "slug"],
                name="speakers_presenter_slug_per_edition",
            ),
        ]

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        if not self.slug:
            self.slug = _unique_slug(
                Presenter, self.conference, self.display_name, exclude_pk=self.pk
            )
        super().save(*args, **kwargs)

    @property
    def tzinfo(self):
        return zoneinfo.ZoneInfo(self.timezone)


class Session(TimestampedModel):
    """Anything that appears on the schedule (design §8.1).

    Workshops, panels and performances, and also the opening, breaks and
    socials: a break is a session with no presenters.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    kind = models.CharField(max_length=16, choices=SessionKind.choices)
    delivery = models.CharField(
        max_length=16, choices=Delivery.choices, default=Delivery.LIVE
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, blank=True)
    summary_md = models.TextField("summary", blank=True, help_text="Markdown.")
    outline_md = models.TextField("outline", blank=True, help_text="Markdown.")
    prerequisites_md = models.TextField(
        "prerequisites", blank=True, help_text="Markdown."
    )
    audience_md = models.TextField("audience", blank=True, help_text="Markdown.")
    notes_md = models.TextField(
        "internal notes", blank=True, help_text="Markdown. Never public."
    )
    level = models.CharField(max_length=16, choices=SessionLevel.choices, blank=True)
    language = models.CharField(
        max_length=10, blank=True, help_text="Language code, e.g. en, pt-br."
    )
    duration_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Defaults from the kind when left blank."
    )
    video_length_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    youtube_url = models.URLField(blank=True)
    youtube_publish_at = models.DateTimeField(null=True, blank=True)
    premiere_location = models.CharField(
        max_length=16,
        choices=PremiereLocation.choices,
        blank=True,
        help_text="Blank uses the edition's default.",
    )
    status = models.CharField(
        max_length=16, choices=SessionStatus.choices, default=SessionStatus.DRAFT
    )
    is_public = models.BooleanField(
        default=False, help_text="Explicit publish switch (design §11.5)."
    )
    presenters = models.ManyToManyField(
        Presenter, through="SessionPresenter", related_name="sessions", blank=True
    )

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "slug"], name="speakers_session_slug_per_edition"
            )
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.duration_minutes is None:
            self.duration_minutes = DEFAULT_DURATION_MINUTES[SessionKind(self.kind)]
        if not self.slug:
            self.slug = _unique_slug(
                Session, self.conference, self.title, exclude_pk=self.pk
            )
        super().save(*args, **kwargs)

    @property
    def is_content(self):
        """Content kinds need a presenter to be confirmed; program kinds don't."""
        return self.kind in CONTENT_KINDS

    @property
    def is_pre_recorded(self):
        return self.delivery == Delivery.PRE_RECORDED

    @property
    def effective_premiere_location(self):
        """The session's own choice, else the edition's default."""
        if self.premiere_location:
            return self.premiere_location
        settings_row = SpeakerSettings.objects.filter(
            conference_id=self.conference_id
        ).first()
        if settings_row is None:
            return PremiereLocation.DISCORD
        return settings_row.default_premiere_location

    @property
    def has_slot(self):
        return ScheduleSlot.objects.filter(session=self).exists()

    @property
    def confirmed_presenter_count(self):
        return self.session_presenters.filter(confirmed_at__isnull=False).count()

    # Status transitions. Each checks its precondition and raises
    # TransitionError otherwise; callers decide how to surface that.

    def _require_status(self, *allowed):
        if self.status not in allowed:
            raise TransitionError(
                f"Cannot do that from status {self.get_status_display()}."
            )

    def mark_invited(self, save=True):
        """DRAFT -> INVITED, when the first invitation goes out."""
        self._require_status(SessionStatus.DRAFT, SessionStatus.INVITED)
        self.status = SessionStatus.INVITED
        if save:
            self.save(update_fields=["status"])

    def confirm(self, save=True):
        """-> CONFIRMED. Content kinds need at least one confirmed presenter."""
        self._require_status(SessionStatus.DRAFT, SessionStatus.INVITED)
        if self.is_content and self.confirmed_presenter_count == 0:
            raise TransitionError(
                "A content session needs at least one confirmed presenter."
            )
        self.status = SessionStatus.CONFIRMED
        if save:
            self.save(update_fields=["status"])

    def schedule(self, save=True):
        """CONFIRMED -> SCHEDULED once a slot exists."""
        self._require_status(SessionStatus.CONFIRMED, SessionStatus.SCHEDULED)
        if not self.has_slot:
            raise TransitionError("Give the session a schedule slot first.")
        self.status = SessionStatus.SCHEDULED
        if save:
            self.save(update_fields=["status"])

    def publish(self, save=True):
        """SCHEDULED -> PUBLISHED and flips ``is_public`` on."""
        self._require_status(SessionStatus.SCHEDULED, SessionStatus.PUBLISHED)
        if not self.has_slot:
            raise TransitionError("A session needs a schedule slot to be published.")
        self.status = SessionStatus.PUBLISHED
        self.is_public = True
        if save:
            self.save(update_fields=["status", "is_public"])

    def cancel(self, save=True):
        """Any status -> CANCELLED; takes the session off the public site."""
        self.status = SessionStatus.CANCELLED
        self.is_public = False
        if save:
            self.save(update_fields=["status", "is_public"])


class SessionPresenter(TimestampedModel):
    """Links a presenter to a session with a role (design §8.3)."""

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="session_presenters",
        editable=False,
    )
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="session_presenters"
    )
    presenter = models.ForeignKey(
        Presenter, on_delete=models.CASCADE, related_name="session_presenters"
    )
    role = models.CharField(
        max_length=16, choices=PresenterRole.choices, default=PresenterRole.PRESENTER
    )
    order = models.PositiveSmallIntegerField(default=0)
    is_required = models.BooleanField(
        default=True,
        help_text="The session is only confirmed once every required presenter "
        "has accepted.",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "presenter"],
                name="speakers_presenter_once_per_session",
            )
        ]

    def __str__(self):
        return f"{self.presenter} ({self.get_role_display()}) on {self.session}"

    def clean(self):
        super().clean()
        if self.session.conference_id != self.presenter.conference_id:
            raise ValidationError(
                "The session and the presenter belong to different editions."
            )

    def save(self, *args, **kwargs):
        self.clean()
        self.conference_id = self.session.conference_id
        super().save(*args, **kwargs)

    @property
    def is_confirmed(self):
        return self.confirmed_at is not None

    def confirm(self, when=None):
        """Record the presenter's acceptance."""
        self.confirmed_at = when or timezone.now()
        self.save(update_fields=["confirmed_at"])


class ScheduleSlot(TimestampedModel):
    """When and where a session happens (design §8.5). Shell for Stage 3.

    ``channel`` null means all channels: the opening or a break spans the
    whole grid. Overlap validation arrives with task 3.1.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="schedule_slots",
        editable=False,
    )
    session = models.OneToOneField(
        Session, on_delete=models.CASCADE, related_name="slot"
    )
    channel = models.ForeignKey(
        DiscordChannel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="slots",
    )
    start_utc = models.DateTimeField()
    end_utc = models.DateTimeField(
        blank=True, help_text="Defaults to start plus the session duration."
    )

    class Meta:
        ordering = ["start_utc"]

    def __str__(self):
        return f"{self.session} at {self.start_utc:%Y-%m-%d %H:%M} UTC"

    def save(self, *args, **kwargs):
        self.conference_id = self.session.conference_id
        if not self.end_utc:
            self.end_utc = self.start_utc + timezone.timedelta(
                minutes=self.session.duration_minutes
            )
        super().save(*args, **kwargs)


class InvitationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Not sent"
    SENT = "SENT", "Sent"
    OPENED = "OPENED", "Opened"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    EXPIRED = "EXPIRED", "Expired"
    CANCELLED = "CANCELLED", "Cancelled"


class Invitation(TimestampedModel):
    """An organizer inviting a presenter, usually to one session (design §8.4).

    ``session`` is null when a panelist is invited to the conference generally.
    The email carries a signed, single-use token that ``send()`` regenerates
    every time, so a resend invalidates the previous link. Timestamps record
    the journey so the sessions list can say "invited 9 days ago, not yet
    accepted".
    """

    TOKEN_MAX_AGE = timedelta(days=14)

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="speaker_invitations",
        editable=False,
    )
    presenter = models.ForeignKey(
        Presenter, on_delete=models.CASCADE, related_name="invitations"
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invitations",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_speaker_invitations",
    )
    message_md = models.TextField(
        "personal message", blank=True, help_text="Markdown, included in the email."
    )
    token = models.CharField(max_length=64, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creation_date", "-id"]

    def __str__(self):
        target = self.session or self.conference
        return f"Invitation for {self.presenter} to {target}"

    def clean(self):
        super().clean()
        if self.session is not None and (
            self.session.conference_id != self.presenter.conference_id
        ):
            raise ValidationError(
                "The session and the presenter belong to different editions."
            )

    def save(self, *args, **kwargs):
        self.clean()
        self.conference_id = self.presenter.conference_id
        super().save(*args, **kwargs)

    @property
    def status(self):
        if self.accepted_at:
            return InvitationStatus.ACCEPTED
        if self.declined_at:
            return InvitationStatus.DECLINED
        if self.cancelled_at:
            return InvitationStatus.CANCELLED
        if self.sent_at is None:
            return InvitationStatus.DRAFT
        if self.expires_at and self.expires_at < timezone.now():
            return InvitationStatus.EXPIRED
        if self.opened_at:
            return InvitationStatus.OPENED
        return InvitationStatus.SENT

    @property
    def is_open(self):
        """Still waiting for an answer and usable."""
        return self.status in (InvitationStatus.SENT, InvitationStatus.OPENED)

    def issue_token(self, now=None):
        """Mint a fresh token and expiry; the previous link stops working."""
        now = now or timezone.now()
        self.token = secrets.token_urlsafe(32)
        self.sent_at = now
        self.expires_at = now + self.TOKEN_MAX_AGE
        self.opened_at = None
        self.declined_at = None
        self.cancelled_at = None
