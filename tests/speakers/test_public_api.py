"""The public JSON API (task 6.2, design §11.1)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from speakers.constants import ProgramVisibility
from speakers.models import AllowedOrigin, Presenter, Session, SpeakerSettings
from speakers.public import preview_token

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_room,
    make_session,
    make_settings,
)

T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


def url(name, *args, conference="2025"):
    return reverse(f"speakers_api:{name}", args=[conference, *args])


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def settings_row(conference):
    row = make_settings(conference, program_visibility=ProgramVisibility.PUBLISHED)
    AllowedOrigin.objects.create(
        settings=row, url="https://2026.conference.pyladies.com/"
    )
    return row


def scheduled_break(conference, start, title):
    """A program item on the published schedule: public with it."""
    session = make_session(conference, kind="BREAK", title=title)
    session.confirm()
    make_published_slot(session, start_utc=start)
    session.schedule()
    return session


def flush_commits():
    """Run what the test's own never-committed transaction has queued, as a
    real commit would, so later saves are not deduplicated against it."""
    for _, callback, _ in connection.run_on_commit:
        callback()
    connection.run_on_commit.clear()


@pytest.fixture
def program(conference, settings_row):
    """A small program with every case the rules care about."""
    room = make_room(conference, name="Main stage", url="https://discord.example/1")
    ada = make_presenter(
        conference,
        display_name="Ada",
        email="ada@example.com",
        pronouns="she/her",
        bio_md="**Hi**<script>alert(1)</script>",
        github_username="ada",
    )
    shy = make_presenter(conference, display_name="Shy", is_public=False)
    undecided = make_presenter(conference, display_name="Undecided")
    talk = make_session(
        conference,
        kind="PANEL",
        title="Python, kindly",
        summary_md="A *gentle* panel.",
        notes_md="SECRET ORGANIZER NOTE",
        duration_minutes=60,
    )
    lead = add_presenter(talk, ada, confirmed=True)
    add_presenter(talk, shy, confirmed=True)
    add_presenter(talk, undecided)
    talk.confirm()
    make_published_slot(
        talk, room=room, start_utc=T0, end_utc=T0 + timedelta(minutes=60)
    )
    talk.schedule()
    talk.publish()
    coffee = make_session(conference, kind="BREAK", title="Coffee")
    coffee.confirm()
    make_published_slot(
        coffee,
        start_utc=T0 + timedelta(hours=1),
        end_utc=T0 + timedelta(hours=1, minutes=15),
    )
    coffee.schedule()
    unticked = make_session(conference, kind="PANEL", title="Not ticked yet")
    add_presenter(
        unticked, make_presenter(conference, display_name="Waiting"), confirmed=True
    )
    unticked.confirm()
    make_published_slot(unticked, start_utc=T0 + timedelta(hours=3))
    unticked.schedule()
    flush_commits()
    return {
        "room": room,
        "ada": Presenter.objects.get(pk=ada.pk),
        "talk": Session.objects.get(pk=talk.pk),
        "coffee": Session.objects.get(pk=coffee.pk),
        "unticked": unticked,
        "role": lead.role.name,
        "shy": shy,
    }


def get(client, path, **params):
    response = client.get(path, params)
    return response, json.loads(response.content)


def _items(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(inner, str):
                yield key, inner
            yield from _items(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _items(inner)


def keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from keys(inner)


@pytest.mark.django_db
class TestSnapshots:
    def test_sessions(self, client, program, conference):
        response, data = get(client, url("sessions"))
        talk, coffee, ada = program["talk"], program["coffee"], program["ada"]
        assert data == {
            "conference": {
                "slug": "2025",
                "name": "PyLadiesCon 2025",
                "timezone": "UTC",
            },
            "program": "published",
            "sessions": [
                {
                    "slug": talk.slug,
                    "title": "Python, kindly",
                    "kind": {"code": "PANEL", "name": talk.kind.name},
                    "is_content": True,
                    "delivery": talk.delivery,
                    "level": None,
                    "language": talk.language or None,
                    "duration_minutes": 60,
                    "summary_md": "A *gentle* panel.",
                    "summary_html": "<p>A <em>gentle</em> panel.</p>",
                    "outline_md": "",
                    "outline_html": "",
                    "prerequisites_md": "",
                    "prerequisites_html": "",
                    "audience_md": "",
                    "audience_html": "",
                    "youtube_url": None,
                    "slot": {
                        "start": "2026-12-05T14:00:00Z",
                        "end": "2026-12-05T15:00:00Z",
                        "room": {
                            "name": "Main stage",
                            "url": "https://discord.example/1",
                        },
                    },
                    "presenters": [
                        {
                            "name": "Ada",
                            "slug": ada.slug,
                            "role": program["role"],
                            "headshot_url": None,
                        },
                        {
                            "name": "Shy",
                            "slug": None,
                            "role": program["role"],
                            "headshot_url": None,
                        },
                    ],
                    "urls": {
                        "ics": f"https://example.com/api/v1/2025/sessions/{talk.slug}.ics"
                    },
                },
                {
                    "slug": coffee.slug,
                    "title": "Coffee",
                    "kind": {"code": "BREAK", "name": "Break"},
                    "is_content": False,
                    "delivery": coffee.delivery,
                    "level": None,
                    "language": coffee.language or None,
                    "duration_minutes": coffee.duration_minutes,
                    "summary_md": "",
                    "summary_html": "",
                    "outline_md": "",
                    "outline_html": "",
                    "prerequisites_md": "",
                    "prerequisites_html": "",
                    "audience_md": "",
                    "audience_html": "",
                    "youtube_url": None,
                    "slot": {
                        "start": "2026-12-05T15:00:00Z",
                        "end": "2026-12-05T15:15:00Z",
                        "room": None,
                    },
                    "presenters": [],
                    "urls": {
                        "ics": f"https://example.com/api/v1/2025/sessions/{coffee.slug}.ics"
                    },
                },
            ],
        }
        assert response["Cache-Control"] == "public, max-age=300"

    def test_one_session(self, client, program):
        talk = program["talk"]
        response, data = get(client, url("session", talk.slug))
        assert data["session"]["title"] == "Python, kindly"
        assert data["program"] == "published"
        assert client.get(url("session", program["unticked"].slug)).status_code == 404
        assert client.get(url("session", "no-such-thing")).status_code == 404

    def test_presenters(self, client, program):
        response, data = get(client, url("presenters"))
        ada, talk = program["ada"], program["talk"]
        assert data["presenters"] == [
            {
                "slug": ada.slug,
                "name": "Ada",
                "pronouns": "she/her",
                "bio_md": "**Hi**<script>alert(1)</script>",
                "bio_html": "<p><strong>Hi</strong></p>",
                "headshot_url": None,
                "location": None,
                "links": {
                    "website": None,
                    "github": "ada",
                    "mastodon": None,
                    "linkedin": None,
                    "bluesky": None,
                },
                "sessions": [
                    {
                        "slug": talk.slug,
                        "title": "Python, kindly",
                        "start": "2026-12-05T14:00:00Z",
                        "end": "2026-12-05T15:00:00Z",
                        "room": {
                            "name": "Main stage",
                            "url": "https://discord.example/1",
                        },
                    }
                ],
            }
        ]

    def test_schedule_groups_by_the_conference_day(self, client, program, conference):
        SpeakerSettings.objects.filter(conference=conference).update(
            conference_timezone="America/Vancouver"
        )
        response, data = get(client, url("schedule"))
        talk, coffee = program["talk"], program["coffee"]
        assert data == {
            "conference": {
                "slug": "2025",
                "name": "PyLadiesCon 2025",
                "timezone": "America/Vancouver",
            },
            "program": "published",
            "timezone": "America/Vancouver",
            "rooms": [{"name": "Main stage", "url": "https://discord.example/1"}],
            "days": [
                {
                    "date": "2026-12-05",
                    "slots": [
                        {
                            "start": "2026-12-05T14:00:00Z",
                            "end": "2026-12-05T15:00:00Z",
                            "room": {
                                "name": "Main stage",
                                "url": "https://discord.example/1",
                            },
                            "session": {
                                "slug": talk.slug,
                                "title": "Python, kindly",
                                "kind": "PANEL",
                                "is_content": True,
                            },
                        },
                        {
                            "start": "2026-12-05T15:00:00Z",
                            "end": "2026-12-05T15:15:00Z",
                            "room": None,
                            "session": {
                                "slug": coffee.slug,
                                "title": "Coffee",
                                "kind": "BREAK",
                                "is_content": False,
                            },
                        },
                    ],
                }
            ],
        }

    def test_a_late_utc_slot_lands_on_the_local_day(self, client, program, conference):
        SpeakerSettings.objects.filter(conference=conference).update(
            conference_timezone="America/Vancouver"
        )
        late = scheduled_break(
            conference,
            datetime(2026, 12, 6, 3, 0, tzinfo=timezone.utc),
            "Late break",
        )
        response, data = get(client, url("schedule"))
        dates = [day["date"] for day in data["days"]]
        assert dates == ["2026-12-05"]
        assert late.slug in [
            slot["session"]["slug"] for slot in data["days"][0]["slots"]
        ]

    def test_headshots_are_absolute(self, client, program):
        Presenter.objects.filter(pk__in=[program["ada"].pk, program["shy"].pk]).update(
            headshot="speakers/headshots/ada.jpg"
        )
        response, data = get(client, url("presenters"))
        assert data["presenters"][0]["headshot_url"].startswith("https://example.com/")
        response, data = get(client, url("session", program["talk"].slug))
        ada, shy = data["session"]["presenters"]
        assert ada["headshot_url"].startswith("https://example.com/")
        # An opt-out keeps the name on the session, never the photo.
        assert shy["headshot_url"] is None

    def test_one_presenter(self, client, program):
        ada = program["ada"]
        response, data = get(client, url("presenter", ada.slug))
        assert data["presenter"]["name"] == "Ada"
        assert data["presenter"]["sessions"][0]["start"] == "2026-12-05T14:00:00Z"
        assert client.get(url("presenter", program["shy"].slug)).status_code == 404
        assert client.get(url("presenter", "nobody")).status_code == 404


@pytest.mark.django_db
class TestNothingLeaks:
    def test_no_email_and_no_internal_notes_anywhere(self, client, program):
        for name, args in [
            ("sessions", []),
            ("presenters", []),
            ("schedule", []),
            ("session", [program["talk"].slug]),
        ]:
            response, data = get(client, url(name, *args))
            body = response.content.decode()
            assert not any("email" in key for key in keys(data)), name
            assert "@example.com" not in body, name
            assert "SECRET ORGANIZER NOTE" not in body, name
            assert "notes" not in set(keys(data)), name
            # The *_md fields are the stored source, as typed; only the
            # *_html fields are meant for a page, and those are sanitized.
            assert not any(
                "<script" in value
                for key, value in _items(data)
                if key.endswith("_html")
            ), name

    def test_the_unpublished_and_the_undecided_are_absent(self, client, program):
        body = client.get(url("sessions")).content.decode()
        assert "Not ticked yet" not in body
        assert "Undecided" not in body
        assert "Waiting" not in client.get(url("presenters")).content.decode()


@pytest.mark.django_db
class TestProgramStates:
    def test_internal_is_empty(self, client, program, conference):
        SpeakerSettings.objects.filter(conference=conference).update(
            program_visibility=ProgramVisibility.INTERNAL
        )
        response, data = get(client, url("sessions"))
        assert data["program"] == "internal"
        assert data["sessions"] == []
        assert get(client, url("presenters"))[1]["presenters"] == []
        assert get(client, url("schedule"))[1]["days"] == []
        response, data = get(client, url("session", program["talk"].slug))
        assert data["session"] is None and data["program"] == "internal"
        response, data = get(client, url("presenter", program["ada"].slug))
        assert data["presenter"] is None and data["program"] == "internal"

    def test_preview_shows_the_draft_and_is_never_cached(
        self, client, program, conference
    ):
        settings_row = SpeakerSettings.objects.get(conference=conference)
        settings_row.program_visibility = ProgramVisibility.INTERNAL
        settings_row.save()
        token = preview_token(settings_row)
        response, data = get(client, url("sessions"), preview=token)
        assert data["program"] == "preview"
        titles = [session["title"] for session in data["sessions"]]
        assert "Not ticked yet" in titles
        assert response["Cache-Control"] == "no-store"
        junk, junk_data = get(client, url("sessions"), preview="garbage")
        assert junk_data["program"] == "internal"
        assert junk_data["sessions"] == []
        assert junk["Cache-Control"] == "public, max-age=300"

    def test_a_junk_token_is_served_from_the_cache(self, client, program):
        """Anyone could otherwise force a rebuild per hit, and blank a CDN,
        by appending a junk parameter."""
        talk = program["talk"]
        assert "Python, kindly" in client.get(url("sessions")).content.decode()
        Session.objects.filter(pk=talk.pk).update(title="Renamed quietly")
        junk, data = get(client, url("sessions"), preview="garbage")
        assert "Python, kindly" in [s["title"] for s in data["sessions"]]
        assert junk["Cache-Control"] == "public, max-age=300"

    def test_unknown_or_disabled_editions_are_404(self, client, program, conference):
        assert client.get(url("sessions", conference="1999")).status_code == 404
        SpeakerSettings.objects.filter(conference=conference).update(
            speaker_module_enabled=False
        )
        assert client.get(url("sessions")).status_code == 404


@pytest.mark.django_db
class TestCache:
    def test_cached_until_a_save(
        self, client, program, django_capture_on_commit_callbacks
    ):
        talk = program["talk"]
        assert "Python, kindly" in client.get(url("sessions")).content.decode()
        # A write that skips the signals proves the response came from cache.
        Session.objects.filter(pk=talk.pk).update(title="Renamed quietly")
        assert "Python, kindly" in client.get(url("sessions")).content.decode()
        with django_capture_on_commit_callbacks(execute=True):
            talk.refresh_from_db()
            talk.save()
        assert "Renamed quietly" in client.get(url("sessions")).content.decode()

    def test_queries_do_not_grow_with_the_program(self, client, program, conference):
        def count():
            cache.clear()
            with CaptureQueriesContext(connection) as context:
                client.get(url("sessions"))
            return len(context)

        before = count()
        for hour in range(5, 9):
            session = make_session(conference, kind="PANEL", title=f"Extra {hour}")
            add_presenter(session, make_presenter(conference), confirmed=True)
            session.confirm()
            make_published_slot(session, start_utc=T0 + timedelta(hours=hour))
            session.schedule()
            session.publish()
        assert count() == before

    def test_one_bump_per_edition_per_transaction(
        self, program, conference, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks() as callbacks:
            program["talk"].save()
            program["coffee"].save()
            program["ada"].save()
        bumps = [c for c in callbacks if getattr(c, "public_api_for", None)]
        assert len(bumps) == 1

    def test_djangos_pending_callbacks_keep_their_shape(self, conference):
        """public_api_changed reads connection.run_on_commit, a private
        structure of (savepoint ids, function, robust) tuples in Django
        5.2; a Django upgrade that changes it should fail here first."""
        from django.db import transaction

        calls = []
        callback = calls.append  # bound once: a fresh bound method is never `is`
        transaction.on_commit(callback)
        entry = connection.run_on_commit[-1]
        assert isinstance(entry, tuple) and len(entry) == 3
        assert entry[1] is callback
        assert calls == []  # the test transaction never commits

    def test_invalidate_starts_a_generation(self, conference):
        from speakers.api import invalidate

        invalidate(conference.pk)
        invalidate(conference.pk)
        assert cache.get(f"speakers-api:{conference.pk}:generation") == 2


@pytest.mark.django_db
class TestCors:
    def test_a_listed_origin_may_read(self, client, program):
        response = client.get(
            url("sessions"), headers={"Origin": "https://2026.conference.pyladies.com"}
        )
        assert (
            response["Access-Control-Allow-Origin"]
            == "https://2026.conference.pyladies.com"
        )
        assert "Origin" in response["Vary"]

    def test_a_preflight_answers_a_listed_origin(self, client, program):
        response = client.options(
            url("sessions"),
            headers={
                "Origin": "https://2026.conference.pyladies.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "if-none-match",
            },
        )
        assert response.status_code == 200
        assert (
            response["Access-Control-Allow-Origin"]
            == "https://2026.conference.pyladies.com"
        )
        assert response["Access-Control-Allow-Methods"] == "GET, HEAD, OPTIONS"
        assert (
            response["Access-Control-Allow-Headers"]
            == "If-None-Match, If-Modified-Since"
        )
        assert response["Access-Control-Max-Age"] == "86400"
        bare = client.options(
            url("sessions"), headers={"Origin": "https://evil.example"}
        )
        assert "Access-Control-Allow-Origin" not in bare
        assert "Access-Control-Allow-Headers" not in bare

    def test_any_other_origin_may_not(self, client, program):
        response = client.get(
            url("sessions"), headers={"Origin": "https://evil.example"}
        )
        assert "Access-Control-Allow-Origin" not in response
        assert "Access-Control-Allow-Origin" not in client.get(url("sessions"))


@pytest.mark.django_db
class TestCalendarAliases:
    def test_schedule_and_session_feeds_per_edition(self, client, program):
        talk = program["talk"]
        assert "Python\\, kindly" in client.get(url("schedule_ics")).content.decode()
        one = client.get(url("session_ics", talk.slug))
        assert one.status_code == 200
        assert "Python\\, kindly" in one.content.decode()
        assert client.get(url("schedule_ics", conference="1999")).status_code == 404


@pytest.mark.django_db
class TestAllowedOrigin:
    def test_stored_as_browsers_send_it(self, settings_row):
        origin = AllowedOrigin.objects.create(
            settings=settings_row, url=" HTTPS://Site.Example:8443/ "
        )
        assert origin.url == "https://site.example:8443"
        assert str(origin) == "https://site.example:8443"
        assert "https://site.example:8443" in settings_row.api_origins

    @pytest.mark.parametrize(
        "url",
        [
            "https://site.example/schedule/",
            "https://site.example/?x=1",
            "https://site.example/#top",
        ],
    )
    def test_only_the_site_address(self, settings_row, url):
        origin = AllowedOrigin(settings=settings_row, url=url)
        with pytest.raises(ValidationError, match="without a page path"):
            origin.full_clean()

    def test_a_bare_address_is_valid(self, settings_row):
        AllowedOrigin(settings=settings_row, url="https://site.example/").full_clean()

    def test_the_admin_edits_the_websites_as_rows(self, client, settings_row):
        admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password=None
        )
        client.force_login(admin)
        content = client.get(
            reverse("admin:speakers_speakersettings_change", args=[settings_row.pk])
        ).content.decode()
        assert "Websites allowed to show the program" in content
        assert 'value="https://2026.conference.pyladies.com"' in content
