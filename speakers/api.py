"""The public JSON API's payloads and cache (task 6.2, design §11.1).

Everything here starts from ``speakers.public``: a session or presenter the
visibility rules do not allow never reaches a payload. Emails never do
either, nor internal notes. Markdown fields come twice, as the stored
source (``*_md``) and as sanitized HTML (``*_html``).
"""

from django.core.cache import cache
from django.db.models import Prefetch
from django.urls import reverse

from .emails import absolute_url
from .markdown import render_md
from .models import Room, SessionPresenter
from .public import program_is_published, public_presenters, public_program

CACHE_SECONDS = 300
SESSION_TEXT = ("summary", "outline", "prerequisites", "audience")


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def site_base():
    """Scheme and host from the configured Site, like the emails: payloads
    are cached and served to everyone, so the first caller's host must not
    leak into them. Read once per response (it is a query) and passed down."""
    return absolute_url("")


def _absolute(base, url):
    """``url`` made absolute on ``base``; one already absolute (Spaces) is
    kept."""
    return base + url if url.startswith("/") else url


def _text(obj, name):
    source = getattr(obj, f"{name}_md")
    return {f"{name}_md": source, f"{name}_html": render_md(source)}


def program_state(conference, previewing):
    if previewing:
        return "preview"
    return "published" if program_is_published(conference) else "internal"


def conference_block(conference):
    return {
        "slug": conference.slug,
        "name": conference.name,
        "timezone": conference.speaker_settings.conference_timezone,
    }


def sessions_queryset(conference, preview=None):
    """The public program with everything a payload reads, in flat queries."""
    public_ids = set(
        public_presenters(conference, preview).values_list("pk", flat=True)
    )
    links = Prefetch(
        "session_presenters",
        queryset=SessionPresenter.objects.filter(confirmed_at__isnull=False)
        .select_related("presenter", "role")
        .order_by("role__sort_order", "presenter__display_name"),
        to_attr="public_links",
    )
    sessions = (
        public_program(conference, preview)
        .select_related("kind", "published_slot", "published_slot__room")
        .prefetch_related(links)
        .order_by("published_slot__start_utc", "title")
    )
    return sessions, public_ids


def slot_block(session):
    row = session.published_slot
    return {
        "start": _stamp(row.start_utc),
        "end": _stamp(row.end_utc),
        "room": (
            {"name": row.room.name, "url": row.room.url or None}
            if row.room_id
            else None
        ),
    }


def session_payload(conference, session, public_ids, base):
    payload = {
        "slug": session.slug,
        "title": session.title,
        "kind": {"code": session.kind.code, "name": session.kind.name},
        "is_content": session.kind.is_content,
        "delivery": session.delivery,
        "level": session.level or None,
        "language": session.language or None,
        "duration_minutes": session.duration_minutes,
    }
    for name in SESSION_TEXT:
        payload.update(_text(session, name))
    payload.update(
        youtube_url=session.youtube_url or None,
        slot=slot_block(session),
        presenters=[
            presenter_link(link, link.presenter_id in public_ids, base)
            for link in session.public_links
        ],
        urls={
            "ics": _absolute(
                base,
                reverse(
                    "speakers_api:session_ics",
                    args=[conference.slug, session.slug],
                ),
            ),
        },
    )
    return payload


def presenter_link(link, public, base):
    """A presenter as their session shows them. One who opted out keeps
    their name but has no profile to link to and no photo."""
    presenter = link.presenter
    return {
        "name": presenter.display_name,
        "slug": presenter.slug if public else None,
        "role": link.role.name,
        "headshot_url": (
            _absolute(base, presenter.headshot.url)
            if public and presenter.headshot
            else None
        ),
    }


def presenter_payload(presenter, sessions, base):
    payload = {
        "slug": presenter.slug,
        "name": presenter.display_name,
        "pronouns": presenter.pronouns or None,
        **_text(presenter, "bio"),
        "headshot_url": (
            _absolute(base, presenter.headshot.url) if presenter.headshot else None
        ),
        "location": presenter.location or None,
        "links": {
            "website": presenter.website_url or None,
            "github": presenter.github_username or None,
            "mastodon": presenter.mastodon_url or None,
            "linkedin": presenter.linkedin_url or None,
            "bluesky": presenter.bluesky_username or None,
        },
        "sessions": sessions,
    }
    return payload


def presenters_data(conference, preview=None, slug=None):
    """Public presenters with their sessions; ``slug`` narrows to one."""
    base = site_base()
    sessions, _ = sessions_queryset(conference, preview)
    by_presenter = {}
    for session in sessions:
        for link in session.public_links:
            by_presenter.setdefault(link.presenter_id, []).append(
                {"slug": session.slug, "title": session.title, **slot_block(session)}
            )
    presenters = public_presenters(conference, preview)
    if slug is not None:
        presenters = presenters.filter(slug=slug)
    return [
        presenter_payload(presenter, by_presenter.get(presenter.pk, []), base)
        for presenter in presenters
    ]


def schedule_data(conference, preview=None):
    """Published slots grouped by the conference's own calendar day, plus
    the rooms; the widget relabels times in the visitor's timezone."""
    settings = conference.speaker_settings
    tz = settings.tzinfo
    sessions, _ = sessions_queryset(conference, preview)
    days = {}
    for session in sessions:
        start = session.published_slot.start_utc
        days.setdefault(start.astimezone(tz).date().isoformat(), []).append(
            {
                **slot_block(session),
                "session": {
                    "slug": session.slug,
                    "title": session.title,
                    "kind": session.kind.code,
                    "is_content": session.kind.is_content,
                },
            }
        )
    return {
        "timezone": settings.conference_timezone,
        "rooms": [
            {"name": room.name, "url": room.url or None}
            for room in Room.objects.filter(conference=conference, is_active=True)
        ],
        "days": [{"date": date, "slots": slots} for date, slots in days.items()],
    }


def _generation_key(conference_id):
    return f"speakers-api:{conference_id}:generation"


def cache_key(conference, request):
    generation = cache.get(_generation_key(conference.pk), 0)
    query = "&".join(
        f"{key}={value}"
        for key, value in sorted(request.GET.items())
        if key != "preview"
    )
    return f"speakers-api:{conference.pk}:{generation}:{request.path}?{query}"


def invalidate(conference_id):
    """Drop every cached payload of an edition, by moving to a new key
    generation rather than deleting keys one by one."""
    key = _generation_key(conference_id)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, None)
