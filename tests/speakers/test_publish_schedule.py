"""Publishing the schedule (task 4.5, design §10.1): the grid is a draft,
and this is the moment speakers learn anything."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from common.models import SentEmail
from speakers.constants import SessionStatus
from speakers.models import ActivityLog, PublishedSlot
from speakers.schedule import publish_schedule, schedule_changes

from .factories import (
    add_presenter,
    make_presenter,
    make_room,
    make_session,
    make_settings,
    make_slot,
)

EDITOR = reverse("speakers:schedule_editor")
PUBLISH = reverse("speakers:schedule_publish")
T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


def confirmed_session(conference, title="Panel", presenter=None):
    session = make_session(conference, title=title, kind="PANEL")
    add_presenter(session, presenter or make_presenter(conference), confirmed=True)
    session.confirm()
    return session


@pytest.mark.django_db
class TestPublishService:
    def test_place_move_remove_through_publishes(self, conference, enabled, organizer):
        room = make_room(conference)
        session = confirmed_session(conference)
        slot = make_slot(session, room=room, start_utc=T0)

        result = publish_schedule(conference, organizer, notify=False)
        assert result == {"placed": 1, "moved": 0, "removed": 0, "told": 0}
        session.refresh_from_db()
        assert session.status == SessionStatus.SCHEDULED
        assert session.identity_locked is True
        row = session.published_slot
        assert (row.room, row.start_utc, row.ics_sequence) == (room, T0, 0)

        slot.start_utc = T0 + timedelta(hours=2)
        slot.end_utc = None
        slot.save()
        assert schedule_changes(conference) == {
            "placed": [],
            "moved": [slot],
            "removed": [],
        }
        publish_schedule(conference, organizer, notify=False)
        row.refresh_from_db()
        assert row.start_utc == T0 + timedelta(hours=2)
        assert row.ics_sequence == 1

        slot.delete()
        result = publish_schedule(conference, organizer, notify=False)
        assert result["removed"] == 1
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED
        assert session.identity_locked is False
        assert not PublishedSlot.objects.filter(session=session).exists()
        assert ActivityLog.objects.filter(action="schedule.published").count() == 3

    def test_a_cancelled_sessions_snapshot_goes_on_the_next_publish(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        make_slot(session, start_utc=T0)
        publish_schedule(conference, organizer, notify=False)
        session.refresh_from_db()
        session.cancel()
        result = publish_schedule(conference, organizer, notify=False)
        assert result["removed"] == 1
        session.refresh_from_db()
        assert session.status == SessionStatus.CANCELLED
        assert not PublishedSlot.objects.filter(session=session).exists()

    def test_the_str_and_the_tasks_lost_payloads(self, conference, enabled, organizer):
        from speakers.tasks import send_schedule_update_task

        session = confirmed_session(conference)
        make_slot(session, start_utc=T0)
        publish_schedule(conference, organizer, notify=False)
        row = session.published_slot
        assert "published for 2026-12-05 14:00 UTC" in str(row)
        stamp = row.published_at.isoformat()
        assert "is gone" in send_schedule_update_task(
            10**6, [[session.pk, "moved"]], stamp
        )
        bystander = make_presenter(conference)
        assert "Nothing left" in send_schedule_update_task(
            bystander.pk, [[10**6, "moved"]], stamp
        )

    def test_publishing_twice_changes_nothing(self, conference, enabled, organizer):
        session = confirmed_session(conference)
        make_slot(session, start_utc=T0)
        publish_schedule(conference, organizer, notify=False)
        result = publish_schedule(conference, organizer, notify=False)
        assert result == {"placed": 0, "moved": 0, "removed": 0, "told": 0}
        assert session.published_slot.ics_sequence == 0


@pytest.mark.django_db
class TestPublishEmails:
    def test_affected_presenters_only(
        self,
        client,
        organizer,
        enabled,
        conference,
        django_capture_on_commit_callbacks,
    ):
        ada = make_presenter(
            conference,
            display_name="Ada",
            email="ada@example.com",
            timezone="Africa/Lagos",
        )
        grace = make_presenter(
            conference, display_name="Grace", email="grace@example.com"
        )
        moved = confirmed_session(conference, title="Moved panel", presenter=ada)
        steady = confirmed_session(conference, title="Steady panel", presenter=grace)
        make_slot(moved, room=make_room(conference), start_utc=T0)
        make_slot(steady, room=make_room(conference), start_utc=T0)
        publish_schedule(conference, organizer, notify=False)
        moved.slot.start_utc = T0 + timedelta(hours=2)
        moved.slot.end_utc = None
        moved.slot.save()

        client.force_login(organizer)
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                PUBLISH + "?day=2026-12-05", {"notify": "on"}, follow=True
            )
        assert "1 presenter(s) were emailed" in response.content.decode()
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == ["ada@example.com"]
        assert "Moved panel" in message.body
        assert "17:00" in message.body  # 16:00 UTC in Lagos
        assert "Africa/Lagos" in message.body
        assert SentEmail.objects.filter(
            template="emails/speakers/schedule_update.md"
        ).exists()

    def test_a_removed_session_is_worded_as_removed(
        self, conference, enabled, organizer, django_capture_on_commit_callbacks
    ):
        ada = make_presenter(conference, email="ada@example.com")
        session = confirmed_session(conference, title="Gone panel", presenter=ada)
        make_slot(session, start_utc=T0)
        publish_schedule(conference, organizer, notify=False)
        session.slot.delete()
        with django_capture_on_commit_callbacks(execute=True):
            publish_schedule(conference, organizer, notify=True)
        assert len(mail.outbox) == 1
        assert "taken off the schedule" in mail.outbox[0].body

    def test_notify_off_is_silent(
        self, client, organizer, enabled, conference, django_capture_on_commit_callbacks
    ):
        session = confirmed_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(PUBLISH, {}, follow=True)
        assert "No emails were sent" in response.content.decode()
        assert mail.outbox == []

    def test_a_redelivered_task_sends_once(
        self, conference, enabled, organizer, django_capture_on_commit_callbacks
    ):
        from speakers.tasks import send_schedule_update_task

        ada = make_presenter(conference, email="ada@example.com")
        session = confirmed_session(conference, presenter=ada)
        make_slot(session, start_utc=T0)
        with django_capture_on_commit_callbacks(execute=True):
            publish_schedule(conference, organizer, notify=True)
        assert len(mail.outbox) == 1
        stamp = session.published_slot.published_at.isoformat()
        result = send_schedule_update_task(ada.pk, [[session.pk, "placed"]], stamp)
        assert "already sent" in result
        assert len(mail.outbox) == 1


@pytest.mark.django_db
class TestPublishView:
    def test_organizer_only(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.post(PUBLISH, {}).status_code == 403

    def test_nothing_to_publish_says_so(self, client, organizer, enabled):
        client.force_login(organizer)
        response = client.post(PUBLISH, {}, follow=True)
        assert "already matches the grid" in response.content.decode()

    def test_editor_shows_the_unpublished_count_and_dirty_cards(
        self, client, organizer, enabled, conference
    ):
        session = confirmed_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        content = client.get(EDITOR, {"day": "2026-12-05"}).content.decode()
        assert "Publish schedule" in content
        assert "schedule-card-dirty" in content
        assert ">1</span>" in content
        publish_schedule(conference, organizer, notify=False)
        content = client.get(EDITOR, {"day": "2026-12-05"}).content.decode()
        assert "schedule-card-dirty" not in content
