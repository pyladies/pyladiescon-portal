import django_tables2 as tables
from django.utils.html import format_html, format_html_join

from .constants import SessionStatus
from .models import Session

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
    kind = tables.Column(accessor="get_kind_display", order_by="kind")
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
                    link.get_role_display(),
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
