import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from .constants import SessionStatus
from .models import InvitationStatus, Presenter, Session

STATUS_BADGE_CLASSES = {
    SessionStatus.PROPOSED: "text-bg-light border",
    SessionStatus.DRAFT: "text-bg-secondary",
    SessionStatus.INVITED: "text-bg-warning",
    SessionStatus.CONFIRMED: "text-bg-info",
    SessionStatus.SCHEDULED: "text-bg-primary",
    SessionStatus.PUBLISHED: "text-bg-success",
    SessionStatus.CANCELLED: "text-bg-dark",
    SessionStatus.REJECTED: "text-bg-light border",
}


def status_badge(session):
    return format_html(
        '<span class="badge {}">{}</span>',
        STATUS_BADGE_CLASSES[SessionStatus(session.status)],
        session.get_status_display(),
    )


class SessionTable(tables.Table):
    """The sessions list (design mockup §3.1): what it is, who is on it,
    where it stands, when it runs, who looks after it."""

    title = tables.Column(linkify=True)
    kind = tables.Column(
        accessor="kind__name", order_by="kind__sort_order", verbose_name="Type"
    )
    presenters = tables.Column(empty_values=(), orderable=False)
    status = tables.Column()
    slot = tables.Column(empty_values=(), orderable=False, verbose_name="Slot")
    videos = tables.Column(empty_values=(), orderable=False, verbose_name="Videos")
    liaison = tables.Column(empty_values=(), orderable=False)

    class Meta:
        model = Session
        fields = ("title", "kind", "presenters", "status", "slot", "videos", "liaison")
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_presenters(self, record):
        links = record.presenter_links
        if not links:
            return format_html('<span class="text-secondary">—</span>')
        return format_html_join(
            ", ",
            '{} <span class="badge text-bg-light border">{}</span>{}',
            (
                (
                    link.presenter.display_name,
                    link.role.name,
                    (
                        ""
                        if link.is_confirmed
                        else format_html(
                            ' <i class="fa-regular fa-clock text-secondary" '
                            'title="Not yet confirmed"></i>'
                        )
                    ),
                )
                for link in links
            ),
        )

    def render_status(self, record):
        return status_badge(record)

    def render_slot(self, record):
        slot = getattr(record, "slot", None)
        if slot is None:
            return ""
        room = slot.room.name if slot.room else "all rooms"
        return format_html("{} · {}", f"{slot.start_utc:%a %H:%M} UTC", room)

    def render_videos(self, record):
        """Where a pre-recorded session's video stands: the raw upload and
        the final cut, from the ``with_video_status`` annotations."""
        if not record.is_pre_recorded:
            return ""
        raw = getattr(record, "raw_video_version", None)
        if raw is None:
            raw_text = format_html(
                '<span class="text-warning-emphasis">{}</span>', "no raw video"
            )
        else:
            seconds = getattr(record, "raw_video_seconds", None)
            length = (
                f" · {seconds // 60} min {seconds % 60:02d} s"
                if seconds is not None
                else ""
            )
            raw_text = format_html("raw v{}{}", raw, length)
        final = getattr(record, "final_cut_version", None)
        final_text = (
            format_html("final cut v{}", final)
            if final is not None
            else format_html('<span class="text-secondary">{}</span>', "no final cut")
        )
        text = format_html("{}<br>{}", raw_text, final_text)
        if getattr(record, "raw_video_thumbnail", None):
            url = reverse(
                "speakers:media_thumbnail", args=[record.slug, record.raw_video_pk]
            )
            return format_html(
                '<div class="d-flex align-items-center gap-2">'
                '<img src="{}" alt="" loading="lazy" width="64" height="36" '
                'class="media-thumb rounded"><div>{}</div></div>',
                url,
                text,
            )
        return text

    def render_liaison(self, record):
        liaisons = record.liaisons
        if not liaisons:
            return ""
        return ", ".join(u.get_full_name() or u.username for u in liaisons)

    def render_title(self, value, record):
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)


INVITATION_BADGE_CLASSES = {
    InvitationStatus.DRAFT: "text-bg-secondary",
    InvitationStatus.SENT: "text-bg-warning",
    InvitationStatus.OPENED: "text-bg-warning",
    InvitationStatus.ACCEPTED: "text-bg-success",
    InvitationStatus.DECLINED: "text-bg-dark",
    InvitationStatus.EXPIRED: "text-bg-danger",
    InvitationStatus.CANCELLED: "text-bg-secondary",
}


def session_list(record):
    """A presenter's sessions, one line each: the title linked, the role."""
    if not record.session_links:
        return format_html('<span class="text-secondary">—</span>')
    return format_html(
        '<ul class="list-unstyled mb-0">{}</ul>',
        format_html_join(
            "",
            '<li><a href="{}">{}</a> <span class="badge text-bg-light border">{}</span></li>',
            (
                (link.session.get_absolute_url(), link.session.title, link.role.name)
                for link in record.session_links
            ),
        ),
    )


def invitation_badge(invitation):
    if invitation is None:
        return format_html('<span class="text-secondary">—</span>')
    status = invitation.status
    return format_html(
        '<span class="badge {}">{}</span>',
        INVITATION_BADGE_CLASSES[status],
        status.label,
    )


class PresenterTable(tables.Table):
    """The presenter list's basic view: who, how to reach them (email and
    Discord), what they are on, where their invitation stands, who looks
    after them."""

    display_name = tables.Column(verbose_name="Name")
    email = tables.Column()
    sessions = tables.Column(verbose_name="Session", empty_values=(), orderable=False)
    discord_username = tables.Column(verbose_name="Discord", orderable=False)
    invitation = tables.Column(empty_values=(), orderable=False)
    liaison = tables.Column(accessor="liaison", orderable=False)

    class Meta:
        model = Presenter
        fields = (
            "display_name",
            "email",
            "sessions",
            "discord_username",
            "invitation",
            "liaison",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_display_name(self, value, record):
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)

    def render_sessions(self, record):
        return session_list(record)

    def render_invitation(self, record):
        return invitation_badge(record.latest_invitation)

    def render_liaison(self, value):
        return value.get_full_name() or value.username


class PresenterDataTable(tables.Table):
    """The Presenters page's data view: one row per presenter with the
    links, Discord username and the rest the team looks up (directory.py
    lists the same columns for the CSV)."""

    display_name = tables.Column(verbose_name="Name")
    pronouns = tables.Column(orderable=False)
    email = tables.Column()
    discord_username = tables.Column(verbose_name="Discord", orderable=False)
    timezone = tables.Column(orderable=False)
    location = tables.Column(orderable=False)
    website_url = tables.Column(verbose_name="Website", orderable=False)
    github_username = tables.Column(verbose_name="GitHub", orderable=False)
    mastodon_url = tables.Column(verbose_name="Mastodon", orderable=False)
    linkedin_url = tables.Column(verbose_name="LinkedIn", orderable=False)
    bluesky_username = tables.Column(verbose_name="Bluesky", orderable=False)
    # empty_values=(): render "no" for a missing photo, not a dash.
    headshot = tables.Column(verbose_name="Photo", orderable=False, empty_values=())
    is_public = tables.Column(verbose_name="Public profile", orderable=False)
    sessions = tables.Column(verbose_name="Session", empty_values=(), orderable=False)
    invitation = tables.Column(empty_values=(), orderable=False)
    liaison = tables.Column(accessor="liaison", orderable=False)

    class Meta:
        model = Presenter
        fields = (
            "display_name",
            "pronouns",
            "email",
            "discord_username",
            "timezone",
            "location",
            "website_url",
            "github_username",
            "mastodon_url",
            "linkedin_url",
            "bluesky_username",
            "headshot",
            "is_public",
            "sessions",
            "invitation",
            "liaison",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm presenter-data",
            "thead": {"class": "table-light"},
        }

    def render_display_name(self, value, record):
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)

    def _link(self, url, text):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>', url, text
        )

    def render_website_url(self, value):
        return self._link(value, value.replace("https://", "").rstrip("/"))

    def render_github_username(self, value):
        return self._link(f"https://github.com/{value}", value)

    def render_mastodon_url(self, value):
        return self._link(value, value.replace("https://", ""))

    def render_linkedin_url(self, value):
        return self._link(value, value.replace("https://", "").rstrip("/"))

    def render_bluesky_username(self, value):
        return self._link(f"https://bsky.app/profile/{value}", value)

    def render_headshot(self, value):
        return "yes" if value else "no"

    def render_is_public(self, value):
        return "yes" if value else "no"

    def render_sessions(self, record):
        return session_list(record)

    def render_invitation(self, record):
        return invitation_badge(record.latest_invitation)

    def render_liaison(self, value):
        return value.get_full_name() or value.username
