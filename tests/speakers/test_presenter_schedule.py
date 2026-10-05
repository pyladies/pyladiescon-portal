"""The presenter's read-only schedule (task 4.3, design §2.4 and §10)."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from speakers.schedule import presenter_schedule

from .factories import (
    add_presenter,
    make_presenter,
    make_room,
    make_session,
    make_settings,
    make_slot,
)

SCHEDULE = reverse("speakers:my_schedule")
T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def speaker(db, conference, enabled):
    """An onboarded presenter in Lagos (UTC+1) with a scheduled session."""
    user = User.objects.create_user(username="ada", email="ada@example.com")
    presenter = make_presenter(
        conference, user=user, display_name="Ada", timezone="Africa/Lagos"
    )
    session = make_session(conference, title="Shipping Django", kind="PANEL")
    add_presenter(session, presenter, confirmed=True)
    session.confirm()
    make_slot(session, room=make_room(conference, name="main-stage"), start_utc=T0)
    session.schedule()
    return presenter


def publish(session):
    session.schedule()
    session.publish()
    return session


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_redirected(self, client, enabled):
        assertRedirects(
            client.get(SCHEDULE), reverse("account_login") + "?next=" + SCHEDULE
        )

    def test_a_plain_user_is_refused(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(SCHEDULE).status_code == 403


@pytest.mark.django_db
class TestVisibility:
    def test_own_draft_shows_and_hides_from_others(self, client, speaker, conference):
        grace_user = User.objects.create_user(
            username="grace", email="grace@example.com"
        )
        grace = make_presenter(
            conference, user=grace_user, display_name="Grace", timezone="UTC"
        )
        public = make_session(conference, title="Published panel", kind="PANEL")
        add_presenter(public, grace, confirmed=True)
        public.confirm()
        make_slot(public, start_utc=T0 + timedelta(hours=2))
        publish(public)

        client.force_login(speaker.user)
        content = client.get(SCHEDULE).content.decode()
        assert "Shipping Django" in content
        assert "Not yet public" in content
        assert "Your session" in content
        assert "Published panel" in content
        assert "schedule-mine" in content

        client.force_login(grace_user)
        content = client.get(SCHEDULE).content.decode()
        assert "Published panel" in content
        assert "Shipping Django" not in content
        assert "Not yet public" not in content

    def test_a_cancelled_session_disappears(self, client, speaker):
        speaker.session_presenters.get().session.cancel()
        client.force_login(speaker.user)
        content = client.get(SCHEDULE).content.decode()
        assert "Shipping Django" not in content
        assert "Nothing is placed on the schedule yet" in content

    def test_empty_state(self, client, conference, enabled):
        user = User.objects.create_user(username="solo", email="solo@example.com")
        presenter = make_presenter(conference, user=user)
        session = make_session(conference, kind="PANEL")
        add_presenter(session, presenter, confirmed=True)
        client.force_login(user)
        content = client.get(SCHEDULE).content.decode()
        assert "Nothing is placed on the schedule yet" in content


@pytest.mark.django_db
class TestPresenterTimezone:
    def test_times_and_days_follow_the_presenter(self, client, speaker, conference):
        late = make_session(conference, title="Midnight crosser", kind="PANEL")
        add_presenter(late, speaker, confirmed=True)
        late.confirm()
        make_slot(late, start_utc=datetime(2026, 12, 5, 23, 30, tzinfo=timezone.utc))
        client.force_login(speaker.user)
        content = client.get(SCHEDULE).content.decode()
        assert "15:00–16:00" in content
        assert "Saturday 5 December" in content
        assert "Sunday 6 December" in content
        assert "00:30–01:30" in content
        assert "Africa/Lagos" in content

    def test_grouping_is_by_local_day(self, speaker, conference):
        days = presenter_schedule(conference, speaker)
        assert [group["day"].isoformat() for group in days] == ["2026-12-05"]
        entry = days[0]["entries"][0]
        assert entry["is_mine"] is True
        assert entry["is_draft"] is True
        assert entry["room"].name == "main-stage"


@pytest.mark.django_db
class TestQueries:
    def test_query_count_is_flat(self, client, speaker, conference):
        client.force_login(speaker.user)
        with CaptureQueriesContext(connection) as before:
            client.get(SCHEDULE)
        for n in range(4):
            session = make_session(conference, title=f"Extra {n}", kind="PANEL")
            add_presenter(session, make_presenter(conference), confirmed=True)
            session.confirm()
            make_slot(session, start_utc=T0 + timedelta(hours=4 + 2 * n))
            publish(session)
        with CaptureQueriesContext(connection) as after:
            client.get(SCHEDULE)
        assert len(after) == len(before)
