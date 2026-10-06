"""The calendar feeds (task 4.4, design §11.3), reading published slots."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Conference
from speakers.constants import PremiereLocation
from speakers.feeds import escape_text, fold, presenter_feed_token
from speakers.schedule import publish_schedule

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_room,
    make_session,
    make_settings,
    make_slot,
)

FEED = reverse("speakers:schedule_feed")
T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


def public_session(conference, title="Public panel", presenter=None, room=None):
    session = make_session(conference, title=title, kind="PANEL")
    add_presenter(session, presenter or make_presenter(conference), confirmed=True)
    session.confirm()
    make_slot(session, room=room, start_utc=T0)
    make_published_slot(session)
    session.schedule()
    session.publish()
    return session


class TestWriter:
    def test_escaping(self):
        assert escape_text("a,b;c\nd\\e") == ("a\\,b" + "\\" + ";c\\nd\\\\e")

    def test_folding(self):
        lines = fold("S" * 80)
        assert lines[0] == "S" * 75
        assert lines[1] == " " + "S" * 5
        assert fold("short") == ["short"]

    def test_folding_never_splits_a_utf8_sequence(self):
        """38 two-byte characters put the 75-octet cut mid-sequence; the
        fold backs off to the character boundary."""
        lines = fold("é" * 38)
        assert lines[0] == "é" * 37
        assert lines[1] == " é"
        assert all(line.encode("utf-8") for line in lines)


@pytest.mark.django_db
class TestPublicFeed:
    def test_structure_and_visibility(self, client, enabled, conference):
        room = make_room(conference, name="main-stage")
        public_session(conference, title="Shown, loudly", room=room)
        hidden = make_session(conference, title="Hidden draft", kind="PANEL")
        add_presenter(hidden, make_presenter(conference), confirmed=True)
        hidden.confirm()
        make_slot(hidden, start_utc=T0 + timedelta(hours=2))
        make_published_slot(hidden)
        response = client.get(FEED)
        assert response["Content-Type"].startswith("text/calendar")
        assert response["Cache-Control"] == "max-age=300"
        text = response.content.decode()
        assert "BEGIN:VCALENDAR\r\n" in text
        assert "SUMMARY:Shown\\, loudly" in text
        assert "DTSTART:20261205T140000Z" in text
        assert "LOCATION:main-stage" in text
        assert "SEQUENCE:0" in text
        assert "Hidden draft" not in text
        assert "UID:session-" in text and "@2025.pyladiescon-portal" in text

    def test_filters(self, client, enabled, conference):
        room = make_room(conference)
        panel = public_session(conference, title="Filtered panel", room=room)
        public_session(conference, title="Other panel", room=make_room(conference))
        assert (
            "Other panel"
            not in client.get(FEED, {"sessions": panel.slug}).content.decode()
        )
        assert "Filtered panel" in client.get(FEED, {"kind": "PANEL"}).content.decode()
        text = client.get(FEED, {"room": room.pk}).content.decode()
        assert "Filtered panel" in text and "Other panel" not in text

    def test_sequence_bumps_when_a_publish_moves(
        self, client, enabled, conference, organizer
    ):
        session = public_session(conference)
        session.slot.start_utc = T0 + timedelta(hours=1)
        session.slot.end_utc = None
        session.slot.save()
        publish_schedule(conference, organizer, notify=False)
        text = client.get(FEED).content.decode()
        assert "SEQUENCE:1" in text
        assert "DTSTART:20261205T150000Z" in text

    def test_cancelled_keeps_its_uid_and_says_so(self, client, enabled, conference):
        session = public_session(conference, title="Called off")
        session.cancel()
        text = client.get(FEED).content.decode()
        assert "Called off" not in text  # no longer public
        # Their own calendar still hears of it through the personal feed.
        presenter = session.session_presenters.get().presenter
        token = presenter_feed_token(presenter)
        personal = client.get(
            reverse("speakers:presenter_feed", args=[token])
        ).content.decode()
        assert "Called off" in personal
        assert "STATUS:CANCELLED" in personal

    def test_youtube_premiere_is_the_location(self, client, enabled, conference):
        session = make_session(conference, title="PyJam set", kind="PYJAM")
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        session.youtube_url = "https://youtube.com/watch?v=x"
        session.premiere_location = PremiereLocation.YOUTUBE
        session.save()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        session.schedule()
        session.publish()
        text = client.get(FEED).content.decode()
        assert "LOCATION:https://youtube.com/watch?v=x" in text

    def test_module_off_is_404(self, client):
        assert client.get(FEED).status_code == 404


@pytest.mark.django_db
class TestSessionFeed:
    def test_public_session_downloads(self, client, enabled, conference):
        session = public_session(conference)
        response = client.get(reverse("speakers:session_feed", args=[session.slug]))
        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]

    def test_unpublished_is_404(self, client, enabled, conference):
        session = make_session(conference, kind="PANEL")
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        response = client.get(reverse("speakers:session_feed", args=[session.slug]))
        assert response.status_code == 404


@pytest.mark.django_db
class TestPersonalFeed:
    def test_own_unpublished_included_others_excluded(
        self, client, enabled, conference
    ):
        user = User.objects.create_user(username="ada", email="a@example.com")
        ada = make_presenter(conference, user=user, display_name="Ada")
        mine = make_session(conference, title="Mine, early", kind="PANEL")
        add_presenter(mine, ada, confirmed=True)
        mine.confirm()
        make_slot(mine, room=make_room(conference), start_utc=T0)
        make_published_slot(mine)
        mine.schedule()
        public_session(conference, title="Someone publics", room=make_room(conference))
        theirs = make_session(conference, title="Theirs hidden", kind="PANEL")
        make_slot(theirs, start_utc=T0 + timedelta(hours=4))
        make_published_slot(theirs)
        token = presenter_feed_token(ada)
        text = client.get(
            reverse("speakers:presenter_feed", args=[token])
        ).content.decode()
        assert "Mine\\, early" in text
        assert "Theirs hidden" not in text
        assert "Someone publics" not in text

    def test_the_sessions_filter_gives_one_session_its_own_feed(
        self, client, enabled, conference
    ):
        user = User.objects.create_user(username="ada", email="a@example.com")
        ada = make_presenter(conference, user=user)
        first = make_session(conference, title="First of mine", kind="PANEL")
        add_presenter(first, ada, confirmed=True)
        make_slot(first, room=make_room(conference), start_utc=T0)
        make_published_slot(first)
        second = make_session(conference, title="Second of mine", kind="PANEL")
        add_presenter(second, ada, confirmed=True)
        make_slot(second, start_utc=T0 + timedelta(hours=3))
        make_published_slot(second)
        token = presenter_feed_token(ada)
        url = reverse("speakers:presenter_feed", args=[token])
        text = client.get(url, {"sessions": first.slug}).content.decode()
        assert "First of mine" in text
        assert "Second of mine" not in text

    def test_bad_or_foreign_tokens_are_404(self, client, enabled, conference):
        other = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        stranger = make_presenter(other)
        assert (
            client.get(reverse("speakers:presenter_feed", args=["garbage"])).status_code
            == 404
        )
        token = presenter_feed_token(stranger)
        assert (
            client.get(reverse("speakers:presenter_feed", args=[token])).status_code
            == 404
        )

    def test_the_schedule_page_links_the_feed(self, client, enabled, conference):
        user = User.objects.create_user(username="ada", email="a@example.com")
        ada = make_presenter(conference, user=user)
        session = make_session(conference, kind="PANEL")
        add_presenter(session, ada, confirmed=True)
        session.confirm()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        client.force_login(user)
        content = client.get(reverse("speakers:my_schedule")).content.decode()
        assert "webcal://" in content
        assert "?sessions=" in content
        assert "Download .ics" in content
        assert "/speakers/feeds/" in content
        assert "From URL" in content
        assert "Add to calendar" in content
        assert "calendar.ics" in content


@pytest.mark.django_db
class TestMySessionFeed:
    def test_own_unpublished_download(self, client, enabled, conference):
        user = User.objects.create_user(username="ada", email="a@example.com")
        ada = make_presenter(conference, user=user)
        session = make_session(conference, title="Mine", kind="PANEL")
        add_presenter(session, ada, confirmed=True)
        session.confirm()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        client.force_login(user)
        response = client.get(reverse("speakers:my_session_feed", args=[session.slug]))
        assert response.status_code == 200
        assert "SUMMARY:Mine" in response.content.decode()

    def test_not_mine_or_not_published_is_404(self, client, enabled, conference):
        user = User.objects.create_user(username="ada", email="a@example.com")
        ada = make_presenter(conference, user=user)
        onboarding = make_session(conference, kind="PANEL")
        add_presenter(onboarding, ada, confirmed=True)
        someone = public_session(conference, title="Someone elses")
        unpublished = make_session(conference, title="No snapshot", kind="PANEL")
        add_presenter(unpublished, ada, confirmed=True)
        make_slot(unpublished, start_utc=T0 + timedelta(hours=6))
        client.force_login(user)
        for slug in (someone.slug, unpublished.slug):
            response = client.get(reverse("speakers:my_session_feed", args=[slug]))
            assert response.status_code == 404
