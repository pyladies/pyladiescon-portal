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
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .constants import (
    OPEN_ITEM_STATUSES,
    SESSION_LANGUAGE,
    AssigneeDefault,
    AutoRule,
    ChannelKind,
    ChecklistScope,
    Delivery,
    DueAnchor,
    ItemOwner,
    ItemStatus,
    MediaKind,
    MediaStatus,
    PremiereLocation,
    SessionLevel,
    SessionStatus,
)
from .querysets import PresenterQuerySet, SessionQuerySet
from .signals import session_confirmed


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
    translation_languages = ArrayField(
        models.CharField(max_length=10),
        default=list,
        blank=True,
        help_text="Language codes the team translates transcripts into; one "
        "post-production item is created per language.",
    )
    default_video_length_limit_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Length limit for pre-recorded videos unless a session says otherwise.",
    )

    class Meta:
        verbose_name = "speaker settings"
        verbose_name_plural = "speaker settings"

    def __str__(self):
        return f"Speaker settings ({self.conference})"

    def save(self, *args, **kwargs):
        """An edition that starts using the module gets the default session
        types and presenter roles (``manage.py seed_program_types`` for any
        later top-up)."""
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating:
            from .program_types import seed_program_types

            seed_program_types(self.conference)


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
    pretix_order = models.ForeignKey(
        "attendee.PretixOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_presenters",
        help_text="Manual link when the presenter registered under another "
        "email address; wins over email matching.",
    )

    objects = PresenterQuerySet.as_manager()

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

    def clean(self):
        # Before validate_constraints runs, so "Ada@Example.com" collides
        # with "ada@example.com" in the form instead of on the database.
        self.email = self.email.strip().lower()
        super().clean()

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

    def get_absolute_url(self):
        return reverse("speakers:presenter_detail", kwargs={"pk": self.pk})

    @property
    def latest_invitation(self):
        """Newest invitation, from the listing prefetch when available."""
        history = getattr(self, "invitation_history", None)
        if history is None:
            return self.invitations.order_by("-creation_date", "-id").first()
        return history[0] if history else None


class PresenterRole(TimestampedModel):
    """What a person is on a session: presenter, panelist, host... (design
    §8.3). Rows per edition, seeded from ``program_types.DEFAULT_ROLES``;
    organizers can add more. ``code`` is the stable key seeds and clones use.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.CASCADE,
        related_name="presenter_roles",
    )
    code = models.CharField(
        max_length=32, help_text="Stable key, e.g. PANELIST; upper case."
    )
    name = models.CharField(max_length=60)
    email_word = models.CharField(
        max_length=40,
        default="speaker",
        help_text='How emails address them: "thank you for being a <word>".',
    )
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive roles are kept on existing rows but not offered.",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "code"], name="speakers_role_code_per_edition"
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        # Before validate_constraints, so "panelist" collides with PANELIST
        # in the form instead of on the database.
        self.code = self.code.strip().upper()
        super().clean()

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class SessionType(TimestampedModel):
    """What a schedule row is (design §8.1): workshop, panel, break...

    Rows per edition, seeded from ``program_types.DEFAULT_SESSION_TYPES``.
    The code never checks for a particular type; it reads the flags here.
    ``roles`` says who can be on a session of this type, and a type with no
    roles (a break) takes no presenters at all.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.CASCADE,
        related_name="session_types",
    )
    code = models.CharField(
        max_length=32, help_text="Stable key, e.g. WORKSHOP; upper case."
    )
    name = models.CharField(max_length=60)
    is_content = models.BooleanField(
        default=True,
        help_text="Needs a confirmed presenter to be confirmed. Off for the "
        "opening, breaks and other program items, which are confirmed as created.",
    )
    default_duration_minutes = models.PositiveIntegerField(default=30)
    default_delivery = models.CharField(
        max_length=16, choices=Delivery.choices, default=Delivery.LIVE
    )
    spans_all_channels = models.BooleanField(
        default=False,
        help_text="On the schedule, takes the whole grid rather than one channel.",
    )
    roles = models.ManyToManyField(
        PresenterRole,
        blank=True,
        related_name="session_types",
        help_text="Who can be on a session of this type.",
    )
    default_role = models.ForeignKey(
        PresenterRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Preselected when adding or inviting a presenter.",
    )
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive types are kept on existing sessions but not offered.",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "code"], name="speakers_type_code_per_edition"
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def clean(self):
        """``default_role`` must be of this edition. Whether it is one of
        ``roles`` is a form-level check (the many-to-many is saved after
        ``full_clean`` in the admin), left to the settings form. The code
        is normalised here so a case variant collides in the form, not on
        the database."""
        self.code = self.code.strip().upper()
        super().clean()
        if (
            self.default_role_id
            and self.default_role.conference_id != self.conference_id
        ):
            raise ValidationError({"default_role": "Pick a role of this edition."})

    @property
    def has_presenters(self):
        """Whether sessions of this type carry people at all."""
        return self.roles.exists()

    def allows(self, role):
        return self.roles.filter(pk=role.pk).exists()


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
    kind = models.ForeignKey(
        SessionType, on_delete=models.PROTECT, related_name="sessions"
    )
    delivery = models.CharField(
        max_length=16,
        choices=Delivery.choices,
        blank=True,
        help_text="Blank takes the type's default; filled in on save.",
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

    objects = SessionQuerySet.as_manager()

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
            self.duration_minutes = self.kind.default_duration_minutes
        if not self.delivery:
            self.delivery = self.kind.default_delivery
        if not self.slug:
            self.slug = _unique_slug(
                Session, self.conference, self.title, exclude_pk=self.pk
            )
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.kind_id and self.kind.conference_id != self.conference_id:
            raise ValidationError({"kind": "Pick a session type of this edition."})
        if self.pk and self.kind_id:
            # Changing the type must not leave anyone in a role it disallows.
            allowed = set(self.kind.roles.values_list("pk", flat=True))
            stuck = [
                link
                for link in self.session_presenters.select_related("presenter", "role")
                if link.role_id not in allowed
            ]
            if stuck:
                names = ", ".join(
                    f"{link.presenter.display_name} ({link.role.name})"
                    for link in stuck
                )
                raise ValidationError(
                    {"kind": f"A {self.kind.name} cannot have: {names}."}
                )

    @property
    def is_content(self):
        """Content types need a presenter to be confirmed; program items don't."""
        return self.kind.is_content

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

    def get_absolute_url(self):
        return reverse("speakers:session_detail", kwargs={"pk": self.pk})

    @property
    def liaisons(self):
        """Distinct liaisons of this session's presenters, for the list."""
        links = getattr(self, "presenter_links", None)
        if links is None:
            links = self.session_presenters.select_related("presenter__liaison")
        seen = {}
        for link in links:
            liaison = link.presenter.liaison
            if liaison is not None and liaison.pk not in seen:
                seen[liaison.pk] = liaison
        return list(seen.values())

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

    def back_to_draft(self, save=True):
        """INVITED -> DRAFT when the last open invitation is gone."""
        self._require_status(SessionStatus.INVITED)
        self.status = SessionStatus.DRAFT
        if save:
            self.save(update_fields=["status"])

    def mark_invited(self, save=True):
        """DRAFT -> INVITED, when the first invitation goes out."""
        self._require_status(SessionStatus.DRAFT, SessionStatus.INVITED)
        self.status = SessionStatus.INVITED
        if save:
            self.save(update_fields=["status"])

    @property
    def blocking_required_items(self):
        """Open required checklist items that keep this session from CONFIRMED."""
        return self.checklist_items.filter(
            is_required=True, status__in=OPEN_ITEM_STATUSES
        )

    def confirm(self, save=True):
        """-> CONFIRMED. Content kinds need at least one confirmed presenter,
        and no required checklist item may still be open. Sends
        ``session_confirmed`` so the session-scope checklist is created.

        With ``save=False`` only the attribute changes: nothing is written
        and no signal is sent, so no session checklist appears. The caller
        must save and send ``session_confirmed`` itself."""
        self._require_status(SessionStatus.DRAFT, SessionStatus.INVITED)
        if self.is_content and self.confirmed_presenter_count == 0:
            raise TransitionError(
                "A content session needs at least one confirmed presenter."
            )
        if self.pk is not None and self.blocking_required_items.exists():
            titles = ", ".join(
                self.blocking_required_items.values_list("title", flat=True)[:3]
            )
            raise TransitionError(f"Required checklist items are still open: {titles}.")
        self.status = SessionStatus.CONFIRMED
        if save:
            self.save(update_fields=["status"])
            session_confirmed.send(sender=Session, session=self)

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
    role = models.ForeignKey(
        PresenterRole, on_delete=models.PROTECT, related_name="session_presenters"
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
        return f"{self.presenter} ({self.role}) on {self.session}"

    def clean(self):
        super().clean()
        if self.session_id is None or self.presenter_id is None:
            return  # a form with a missing field reports that itself
        if self.session.conference_id != self.presenter.conference_id:
            raise ValidationError(
                "The session and the presenter belong to different editions."
            )
        if self.role_id is None:
            return  # the field itself already failed validation
        if self.role.conference_id != self.session.conference_id:
            raise ValidationError({"role": "Pick a role of this edition."})
        if not self.session.kind.allows(self.role):
            raise ValidationError(
                {
                    "role": f"A {self.session.kind.name} cannot have a "
                    f"{self.role.name.lower()}."
                }
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
            self.end_utc = self.start_utc + timedelta(
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
    sent_to = models.EmailField(
        blank=True,
        editable=False,
        help_text="The address the current link went to. Accepting verifies "
        "this address, not whatever the presenter's email says later.",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="First visit of the link. A soft signal only: mail scanners "
        'and link previews open links too, so never nag on "not opened".',
    )
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
        self.sent_to = self.presenter.email
        self.sent_at = now
        self.expires_at = now + self.TOKEN_MAX_AGE
        self.opened_at = None
        self.declined_at = None
        self.cancelled_at = None


class ChecklistTemplate(TimestampedModel):
    """An organizer-defined checklist (design §9.1).

    Presenter scope is keyed by session kind and role and instantiated once
    per presenter per session; session scope is keyed by kind and delivery
    and instantiated once per session.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="checklist_templates",
    )
    scope = models.CharField(max_length=16, choices=ChecklistScope.choices)
    name = models.CharField(max_length=100)
    kind = models.ForeignKey(
        SessionType, on_delete=models.PROTECT, related_name="checklist_templates"
    )
    role = models.ForeignKey(
        PresenterRole,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="checklist_templates",
        help_text="Presenter templates only.",
    )
    delivery = models.CharField(
        max_length=16,
        choices=Delivery.choices,
        blank=True,
        help_text="Session scope only.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["scope", "kind", "role", "delivery"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "scope", "kind", "role", "delivery"],
                nulls_distinct=False,
                name="speakers_template_key_per_edition",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.scope == ChecklistScope.PRESENTER and not self.role_id:
            raise ValidationError({"role": "Presenter templates need a role."})
        if self.scope == ChecklistScope.SESSION and not self.delivery:
            raise ValidationError({"delivery": "Session templates need a delivery."})
        if self.scope == ChecklistScope.PRESENTER and self.delivery:
            raise ValidationError({"delivery": "Only session templates use delivery."})
        if self.scope == ChecklistScope.SESSION and self.role_id:
            raise ValidationError({"role": "Only presenter templates use a role."})
        if self.kind_id and self.kind.conference_id != self.conference_id:
            raise ValidationError({"kind": "Pick a session type of this edition."})
        if self.role_id and self.role.conference_id != self.conference_id:
            raise ValidationError({"role": "Pick a role of this edition."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def for_presenter(cls, session, role):
        """The active presenter-scope template for this session type and role."""
        return cls.objects.filter(
            conference_id=session.conference_id,
            scope=ChecklistScope.PRESENTER,
            kind=session.kind,
            role=role,
            is_active=True,
        ).first()

    @classmethod
    def for_session(cls, session):
        """The active session-scope template for this session's type and delivery."""
        return cls.objects.filter(
            conference_id=session.conference_id,
            scope=ChecklistScope.SESSION,
            kind=session.kind,
            delivery=session.delivery,
            is_active=True,
        ).first()


class ChecklistTemplateItem(TimestampedModel):
    """One line of a template (design §9.1 table)."""

    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE, related_name="items"
    )
    order = models.PositiveSmallIntegerField(default=0)
    owner = models.CharField(max_length=16, choices=ItemOwner.choices)
    title = models.CharField(max_length=200)
    description_md = models.TextField(blank=True, help_text="Markdown.")
    due_anchor = models.CharField(max_length=32, choices=DueAnchor.choices, blank=True)
    due_offset_days = models.IntegerField(
        default=0,
        help_text="Days after the invitation is accepted, or days before the "
        "conference or session starts.",
    )
    auto_complete_rule = models.CharField(
        max_length=32, choices=AutoRule.choices, blank=True
    )
    requires_asset_kind = models.CharField(
        max_length=16, choices=MediaKind.choices, blank=True
    )
    requires_asset_language = models.CharField(
        max_length=10,
        blank=True,
        help_text=f'A language code, or "{SESSION_LANGUAGE}" for the session language.',
    )
    per_translation_language = models.BooleanField(
        default=False,
        help_text="Instantiate one item per translation language of the edition.",
    )
    is_required = models.BooleanField(
        default=False, help_text="Required items gate the session being confirmed."
    )
    assignee_default = models.CharField(
        max_length=16,
        choices=AssigneeDefault.choices,
        default=AssigneeDefault.UNASSIGNED,
        help_text="Organizer items only.",
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.auto_complete_rule and self.auto_complete_rule not in AutoRule.values:
            raise ValidationError(
                {"auto_complete_rule": f"Unknown rule {self.auto_complete_rule!r}."}
            )
        if self.requires_asset_kind and not self.auto_complete_rule:
            raise ValidationError(
                {
                    "auto_complete_rule": (
                        "An item that requires an asset needs a rule; "
                        'pick "Asset exists".'
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_automatic(self):
        return bool(self.auto_complete_rule)

    def due_date(
        self, *, invitation_accepted=None, conference_start=None, session_start=None
    ):
        """The due date for one instance, or None when the anchor is unknown.

        ``invitation_accepted`` adds the offset; the two start anchors
        subtract it (the offset is "days before").
        """
        if self.due_anchor == DueAnchor.INVITATION_ACCEPTED:
            base, sign = invitation_accepted, 1
        elif self.due_anchor == DueAnchor.CONFERENCE_START:
            base, sign = conference_start, -1
        elif self.due_anchor == DueAnchor.SESSION_START:
            base, sign = session_start, -1
        else:
            return None
        if base is None:
            return None
        if hasattr(base, "date"):
            base = base.date()
        return base + timedelta(days=sign * self.due_offset_days)


class ChecklistItem(TimestampedModel):
    """One instantiated checklist line (design §9.2).

    Presenter-scope items carry both ``presenter`` and ``session``;
    session-scope items only ``session``. ``template_item`` is null for
    one-off items organizers add by hand. Everything the template said is
    copied onto the instance so later template edits change nothing here
    unless an organizer back-fills them.
    """

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="checklist_items",
    )
    template_item = models.ForeignKey(
        ChecklistTemplateItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
    )
    presenter = models.ForeignKey(
        Presenter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="checklist_items",
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="checklist_items",
    )
    order = models.PositiveSmallIntegerField(default=0)
    owner = models.CharField(max_length=16, choices=ItemOwner.choices)
    title = models.CharField(max_length=200)
    description_md = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=ItemStatus.choices, default=ItemStatus.TODO
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_checklist_items",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    is_required = models.BooleanField(default=False)
    auto_complete_rule = models.CharField(
        max_length=32, choices=AutoRule.choices, blank=True
    )
    requires_asset_kind = models.CharField(
        max_length=16, choices=MediaKind.choices, blank=True
    )
    requires_asset_language = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            # One instance per template line per presenter/session (and per
            # language for the translate items). Ad-hoc items are exempt.
            models.UniqueConstraint(
                fields=[
                    "template_item",
                    "presenter",
                    "session",
                    "requires_asset_language",
                ],
                name="speakers_item_once_per_target",
                condition=models.Q(template_item__isnull=False),
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(presenter__isnull=False)
                | models.Q(session__isnull=False),
                name="speakers_item_has_target",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_automatic(self):
        return bool(self.auto_complete_rule)

    @property
    def is_open(self):
        return self.status in OPEN_ITEM_STATUSES

    @property
    def is_done(self):
        return self.status == ItemStatus.DONE

    @property
    def is_overdue(self):
        return (
            self.is_open
            and self.due_date is not None
            and self.due_date < timezone.now().date()
        )


class MediaAsset(TimestampedModel):
    """A file moving through post-production (design §8.8). Shell for
    Stage 3b: the multipart upload and probing arrive with tasks 4.1-4.3."""

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="media_assets",
        editable=False,
    )
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="media_assets"
    )
    kind = models.CharField(max_length=16, choices=MediaKind.choices)
    language = models.CharField(
        max_length=10, blank=True, help_text="Transcripts and translations."
    )
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=MediaStatus.choices, default=MediaStatus.UPLOADING
    )
    file = models.FileField(upload_to="speakers/media/", blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    notes_md = models.TextField(blank=True, help_text="Reviewer notes. Markdown.")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_media_assets",
    )

    class Meta:
        ordering = ["-version", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} v{self.version} for {self.session}"

    def save(self, *args, **kwargs):
        self.conference_id = self.session.conference_id
        super().save(*args, **kwargs)

    @property
    def is_ready(self):
        return self.status == MediaStatus.READY

    @classmethod
    def latest_ready(cls, session, kind, language=None):
        """The newest READY asset of ``kind`` on ``session`` (and language)."""
        queryset = cls.objects.filter(
            session=session, kind=kind, status=MediaStatus.READY
        )
        if language:
            queryset = queryset.filter(language=language)
        return queryset.order_by("-version", "-id").first()


class Handbook(TimestampedModel):
    """The speaker guide, versioned (design §8.7). Shell for task 2.9."""

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="handbooks",
    )
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, default="Speaker guide")
    body_md = models.TextField(blank=True, help_text="Markdown.")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "version"], name="speakers_handbook_version"
            )
        ]

    def __str__(self):
        return f"{self.title} v{self.version}"

    @classmethod
    def current(cls, conference):
        """The newest published version, or None."""
        return (
            cls.objects.filter(conference=conference, published_at__isnull=False)
            .order_by("-version")
            .first()
        )


class HandbookReadReceipt(TimestampedModel):
    """A presenter read one version of the guide."""

    conference = models.ForeignKey(
        "portal.Conference",
        on_delete=models.PROTECT,
        related_name="handbook_receipts",
        editable=False,
    )
    presenter = models.ForeignKey(
        Presenter, on_delete=models.CASCADE, related_name="handbook_receipts"
    )
    handbook = models.ForeignKey(
        Handbook, on_delete=models.CASCADE, related_name="receipts"
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["presenter", "handbook"], name="speakers_receipt_once"
            )
        ]

    def __str__(self):
        return f"{self.presenter} read {self.handbook}"

    def save(self, *args, **kwargs):
        self.conference_id = self.handbook.conference_id
        super().save(*args, **kwargs)
