import django_tables2 as tables
from django.utils.html import format_html, format_html_join

from .constants import SessionStatus
from .models import InvitationStatus, Presenter, Session

STATUS_BADGE_CLASSES = {
    SessionStatus.DRAFT: "text-bg-secondary",
    SessionStatus.INVITED: "text-bg-warning",
    SessionStatus.CONFIRMED: "text-bg-info",
    SessionStatus.SCHEDULED: "text-bg-primary",
    SessionStatus.PUBLISHED: "text-bg-success",
    SessionStatus.CANCELLED: "text-bg-dark",
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
    liaison = tables.Column(empty_values=(), orderable=False)

    class Meta:
        model = Session
        fields = ("title", "kind", "presenters", "status", "slot", "liaison")
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
        channel = slot.channel.name if slot.channel else "all channels"
        return format_html("{} · {}", f"{slot.start_utc:%a %H:%M} UTC", channel)

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
    """The presenter list: who, how to reach them, what they are on, where
    their invitation stands, who looks after them."""

    display_name = tables.Column(verbose_name="Name")
    email = tables.Column()
    sessions = tables.Column(empty_values=(), orderable=False)
    invitation = tables.Column(empty_values=(), orderable=False)
    account = tables.Column(empty_values=(), orderable=False)
    liaison = tables.Column(accessor="liaison", orderable=False)

    class Meta:
        model = Presenter
        fields = (
            "display_name",
            "email",
            "sessions",
            "invitation",
            "account",
            "liaison",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_display_name(self, value, record):
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)

    def render_sessions(self, record):
        if not record.session_links:
            return format_html('<span class="text-secondary">—</span>')
        return format_html_join(
            ", ",
            '<a href="{}">{}</a> <span class="badge text-bg-light border">{}</span>',
            (
                (
                    link.session.get_absolute_url(),
                    link.session.title,
                    link.role.name,
                )
                for link in record.session_links
            ),
        )

    def render_invitation(self, record):
        return invitation_badge(record.latest_invitation)

    def render_account(self, record):
        if record.user_id is None:
            return format_html('<span class="text-secondary">not yet</span>')
        return format_html('<i class="fa-solid fa-check text-success"></i> linked')

    def render_liaison(self, value):
        return value.get_full_name() or value.username
