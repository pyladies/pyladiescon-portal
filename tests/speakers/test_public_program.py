"""The public program (task 6.1, design §11.5): three switches, one helper,
and a preview link for the website build."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from portal.models import Conference
from speakers.constants import ProgramVisibility, SessionStatus
from speakers.models import ActivityLog, SpeakerSettings
from speakers.public import (
    preview_is_valid,
    preview_token,
    public_presenters,
    public_program,
    regenerate_preview,
)

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_session,
    make_settings,
)

T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)
FEED = reverse("speakers:schedule_feed")
PUBLISHING = reverse("speakers:program_publishing")
INTERNAL = ProgramVisibility.INTERNAL
PUBLISHED = ProgramVisibility.PUBLISHED


@pytest.fixture
def settings_row(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


def go(settings_row, visibility):
    settings_row.program_visibility = visibility
    settings_row.save(update_fields=["program_visibility"])


_hours = iter(range(10_000))


def on_schedule(conference, kind="PANEL", publish=False, presenter=None, title=None):
    """A session somebody accepted, on the published schedule."""
    session = make_session(conference, kind=kind, title=title or f"{kind} session")
    if session.is_content:
        add_presenter(session, presenter or make_presenter(conference), confirmed=True)
    session.confirm()
    make_published_slot(session, start_utc=T0 + timedelta(hours=next(_hours)))
    session.schedule()
    if publish:
        session.publish()
    return session


def confirmed_only(conference, presenter=None):
    """Accepted, but not on the published schedule."""
    session = make_session(conference, kind="PANEL", title="Waiting for a slot")
    add_presenter(session, presenter or make_presenter(conference), confirmed=True)
    session.confirm()
    return session


@pytest.mark.django_db
class TestThreeSwitches:
    @pytest.mark.parametrize(
        "visibility, kind, scheduled, published, shown",
        [
            # Content sessions: all three switches must be on.
            (PUBLISHED, "PANEL", True, True, True),
            (INTERNAL, "PANEL", True, True, False),
            (PUBLISHED, "PANEL", True, False, False),
            (PUBLISHED, "PANEL", False, False, False),
            (INTERNAL, "PANEL", False, False, False),
            # Program items go public with the schedule, no tick needed.
            (PUBLISHED, "BREAK", True, False, True),
            (INTERNAL, "BREAK", True, False, False),
            (PUBLISHED, "BREAK", False, False, False),
        ],
    )
    def test_the_table(
        self, conference, settings_row, visibility, kind, scheduled, published, shown
    ):
        go(settings_row, visibility)
        if scheduled:
            session = on_schedule(conference, kind=kind, publish=published)
        else:
            session = make_session(conference, kind=kind)
            if kind == "BREAK":
                session.confirm()
        assert (session in public_program(conference)) is shown

    def test_a_cancelled_session_leaves(self, conference, settings_row):
        go(settings_row, PUBLISHED)
        session = on_schedule(conference, publish=True)
        session.cancel()
        assert session not in public_program(conference)

    def test_no_settings_row_means_nothing_public(self, conference):
        assert not public_program(conference).exists()


@pytest.mark.django_db
class TestPresenters:
    def test_public_through_a_published_session_only(self, conference, settings_row):
        go(settings_row, PUBLISHED)
        shown = make_presenter(conference, display_name="Shown")
        on_schedule(conference, publish=True, presenter=shown)
        waiting = make_presenter(conference, display_name="Waiting")
        confirmed_only(conference, presenter=waiting)
        unpublished = make_presenter(conference, display_name="Unpublished")
        on_schedule(conference, presenter=unpublished)
        assert list(public_presenters(conference)) == [shown]

    def test_an_opt_out_hides_the_profile_not_the_session(
        self, conference, settings_row
    ):
        go(settings_row, PUBLISHED)
        private = make_presenter(conference, is_public=False)
        session = on_schedule(conference, publish=True, presenter=private)
        assert session in public_program(conference)
        assert not public_presenters(conference).exists()

    def test_an_unanswered_link_is_not_a_public_profile(self, conference, settings_row):
        go(settings_row, PUBLISHED)
        session = on_schedule(conference, publish=True)
        invited = make_presenter(conference, display_name="Still deciding")
        add_presenter(session, invited, role="PANELIST")
        assert invited not in public_presenters(conference)

    def test_internal_program_has_no_public_presenters(self, conference, settings_row):
        on_schedule(conference, publish=True)
        assert not public_presenters(conference).exists()


@pytest.mark.django_db
class TestPreview:
    def test_the_preview_shows_the_draft(self, conference, settings_row):
        draft = on_schedule(conference, title="Not published yet")
        waiting = confirmed_only(conference)
        token = preview_token(settings_row)
        assert preview_is_valid(conference, token)
        program = public_program(conference, preview=token)
        assert draft in program
        assert waiting not in program
        assert public_presenters(conference, preview=token).count() == 1

    def test_a_token_from_another_edition_is_rejected(self, conference, settings_row):
        on_schedule(conference)
        other = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        foreign = preview_token(make_settings(other))
        assert not preview_is_valid(conference, foreign)
        assert not public_program(conference, preview=foreign).exists()

    def test_regenerating_revokes_older_links(self, conference, settings_row):
        old = preview_token(settings_row)
        assert preview_token(settings_row) == old
        new = regenerate_preview(settings_row)
        assert new != old
        assert not preview_is_valid(conference, old)
        assert preview_is_valid(conference, new)

    def test_the_link_stops_when_the_program_goes_public(
        self, conference, settings_row
    ):
        token = preview_token(settings_row)
        go(settings_row, PUBLISHED)
        assert not preview_is_valid(conference, token)

    @pytest.mark.parametrize("token", [None, "", "garbage", "a:b:c"])
    def test_junk_is_rejected(self, conference, settings_row, token):
        preview_token(settings_row)
        assert not preview_is_valid(conference, token)

    def test_a_cleared_key_rejects(self, conference, settings_row):
        token = preview_token(settings_row)
        SpeakerSettings.objects.filter(pk=settings_row.pk).update(preview_key="")
        # A fresh edition object: the settings row is cached on the instance.
        assert not preview_is_valid(Conference.objects.get(pk=conference.pk), token)


@pytest.mark.django_db
class TestFeeds:
    def test_the_public_feed_is_empty_while_internal(
        self, client, conference, settings_row
    ):
        on_schedule(conference, publish=True, title="Ready panel")
        response = client.get(FEED)
        assert "Ready panel" not in response.content.decode()
        assert response["Cache-Control"] == "max-age=300"
        go(settings_row, PUBLISHED)
        assert "Ready panel" in client.get(FEED).content.decode()

    def test_a_preview_feed_shows_the_draft_and_is_never_cached(
        self, client, conference, settings_row
    ):
        session = on_schedule(conference, title="Draft panel")
        token = preview_token(settings_row)
        response = client.get(FEED, {"preview": token})
        assert "Draft panel" in response.content.decode()
        assert response["Cache-Control"] == "no-store"
        one = client.get(
            reverse("speakers:session_feed", args=[session.slug]), {"preview": token}
        )
        assert one.status_code == 200
        assert one["Cache-Control"] == "no-store"
        junk = client.get(FEED, {"preview": "garbage"})
        assert "Draft panel" not in junk.content.decode()
        assert junk["Cache-Control"] == "no-store"


@pytest.mark.django_db
class TestUnpublish:
    def test_back_to_scheduled_with_the_slot_kept(self, conference, settings_row):
        session = on_schedule(conference, publish=True)
        session.unpublish()
        session.refresh_from_db()
        assert session.status == SessionStatus.SCHEDULED
        assert session.is_public is False
        assert session.has_published_slot


@pytest.mark.django_db
class TestPublishingPage:
    def test_organizers_only(self, client, conference, settings_row):
        user = User.objects.create_user(username="someone", email="s@example.com")
        client.force_login(user)
        assert client.get(PUBLISHING).status_code == 403

    def test_ticks_wait_for_the_schedule(
        self, client, organizer, conference, settings_row
    ):
        on_schedule(conference, title="Placed panel")
        confirmed_only(conference)
        on_schedule(conference, kind="BREAK")
        client.force_login(organizer)
        content = client.get(PUBLISHING).content.decode()
        assert "Placed panel" in content
        assert "Not on the published schedule yet" in content
        assert content.count("disabled") == 1
        assert "1 is on it now" in content
        assert "?preview=" in content

    def test_ticking_publishes_and_unticking_takes_off(
        self, client, organizer, conference, settings_row
    ):
        stays = on_schedule(conference, title="Stays")
        goes = on_schedule(conference, publish=True, title="Goes")
        waiting = confirmed_only(conference)
        client.force_login(organizer)
        response = client.post(
            PUBLISHING,
            {"action": "sessions", "publish": [stays.slug, waiting.slug]},
            follow=True,
        )
        assert "1 published, 1 taken off." in response.content.decode()
        stays.refresh_from_db()
        goes.refresh_from_db()
        waiting.refresh_from_db()
        assert stays.status == SessionStatus.PUBLISHED and stays.is_public
        assert goes.status == SessionStatus.SCHEDULED and not goes.is_public
        assert waiting.status == SessionStatus.CONFIRMED
        actions = set(ActivityLog.objects.values_list("action", flat=True))
        assert {"session.published", "session.unpublished"} <= actions
        again = client.post(
            PUBLISHING, {"action": "sessions", "publish": [stays.slug]}, follow=True
        )
        assert "Nothing changed." in again.content.decode()

    def test_the_master_switch(self, client, organizer, conference, settings_row):
        client.force_login(organizer)
        response = client.post(
            PUBLISHING, {"action": "visibility", "visibility": PUBLISHED}, follow=True
        )
        assert "The program is public." in response.content.decode()
        assert "preview links are switched off" in response.content.decode()
        settings_row.refresh_from_db()
        assert settings_row.program_visibility == PUBLISHED
        assert ActivityLog.objects.filter(action="program.visibility").count() == 1
        client.post(PUBLISHING, {"action": "visibility", "visibility": PUBLISHED})
        assert ActivityLog.objects.filter(action="program.visibility").count() == 1
        back = client.post(
            PUBLISHING, {"action": "visibility", "visibility": INTERNAL}, follow=True
        )
        assert "internal again" in back.content.decode()

    def test_regenerate(self, client, organizer, conference, settings_row):
        old = preview_token(settings_row)
        client.force_login(organizer)
        response = client.post(PUBLISHING, {"action": "regenerate"}, follow=True)
        assert "Every earlier link has stopped working." in response.content.decode()
        assert not preview_is_valid(Conference.objects.get(pk=conference.pk), old)
        assert ActivityLog.objects.filter(action="program.preview_regenerated").exists()

    @pytest.mark.parametrize(
        "data",
        [{"action": "nonsense"}, {"action": "visibility", "visibility": "LOUD"}, {}],
    )
    def test_mangled_posts_answer_400(
        self, client, organizer, conference, settings_row, data
    ):
        client.force_login(organizer)
        assert client.post(PUBLISHING, data).status_code == 400

    def test_the_rail_links_it(self, client, organizer, conference, settings_row):
        client.force_login(organizer)
        content = client.get(reverse("speakers:schedule_editor")).content.decode()
        assert PUBLISHING in content


@pytest.mark.django_db
class TestReview466:
    def test_a_get_of_the_page_writes_nothing(
        self, client, organizer, conference, settings_row
    ):
        """The key is minted when the settings row is created, so showing
        the token is a pure read."""
        key = settings_row.preview_key
        assert key
        client.force_login(organizer)
        assert client.get(PUBLISHING).status_code == 200
        settings_row.refresh_from_db()
        assert settings_row.preview_key == key

    def test_one_settings_read_per_program_call(self, conference, settings_row):
        token = preview_token(settings_row)
        edition = Conference.objects.get(pk=conference.pk)
        with CaptureQueriesContext(connection) as context:
            list(public_program(edition, preview=token))
            list(public_program(edition))
        settings_reads = [
            q for q in context.captured_queries if "speakersettings" in q["sql"]
        ]
        assert len(settings_reads) == 1

    def test_no_settings_row_is_read_once_too(self, conference):
        edition = Conference.objects.get(pk=conference.pk)
        with CaptureQueriesContext(connection) as context:
            assert not public_program(edition).exists()
            assert not preview_is_valid(edition, "x")
        assert sum("speakersettings" in q["sql"] for q in context.captured_queries) == 1

    def test_the_migration_keeps_todays_public_sessions_public(
        self, conference, settings_row
    ):
        """0019: an edition with a public session on the confirmed schedule
        starts PUBLISHED; one without starts INTERNAL; each gets its own
        key."""
        on_schedule(conference, publish=True)
        other = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        quiet = make_settings(other)
        SpeakerSettings.objects.update(preview_key="same-for-all")
        migration = importlib.import_module(
            "speakers.migrations.0019_program_visibility"
        )
        migration.settle_each_edition(apps, None)
        settings_row.refresh_from_db()
        quiet.refresh_from_db()
        assert settings_row.program_visibility == PUBLISHED
        assert quiet.program_visibility == INTERNAL
        assert settings_row.preview_key != quiet.preview_key
        assert "same-for-all" not in (settings_row.preview_key, quiet.preview_key)
