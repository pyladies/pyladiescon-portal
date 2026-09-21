from datetime import date, datetime, timedelta, timezone
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from speakers.checklists import add_adhoc_item, complete_item
from speakers.constants import ItemOwner
from speakers.models import ReminderLog
from speakers.reminders import send_checklist_digests
from speakers.tasks import send_checklist_digests_task

from .factories import make_presenter, make_session, make_settings

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


def days(n):
    return TODAY + timedelta(days=n)


@pytest.mark.django_db
class TestSpeakerDigest:
    def test_one_email_per_presenter_with_due_items(self, conference, enabled):
        ada = make_presenter(conference, display_name="Ada", email="ada@example.com")
        session = make_session(conference, title="Django 101")
        soon = add_adhoc_item(
            conference,
            "Read the guide",
            ItemOwner.SPEAKER,
            presenter=ada,
            session=session,
            due_date=days(3),
        )
        later = add_adhoc_item(
            conference,
            "Tech check",
            ItemOwner.SPEAKER,
            presenter=ada,
            due_date=days(20),
        )
        undated = add_adhoc_item(
            conference, "Whenever", ItemOwner.SPEAKER, presenter=ada
        )
        done = add_adhoc_item(
            conference, "Done", ItemOwner.SPEAKER, presenter=ada, due_date=days(1)
        )
        complete_item(done)
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 1
        message = mail.outbox[0]
        assert message.to == ["ada@example.com"]
        assert "1 thing(s) coming up" in message.subject
        assert "Read the guide" in message.body and "Django 101" in message.body
        assert "Tech check" not in message.body and "Whenever" not in message.body
        assert "/speakers/me/" in message.body
        assert "dates in UTC" in message.body
        logs = list(ReminderLog.objects.order_by("threshold_days"))
        assert [(log.item, log.threshold_days) for log in logs] == [
            (soon, 3),
            (soon, 7),
        ]
        assert (
            logs[0].recipient == "ada@example.com" and logs[0].conference == conference
        )
        assert str(logs[0]) == "Read the guide (3d) to ada@example.com"
        assert later.reminders.count() == 0 and undated.reminders.count() == 0

    def test_running_twice_on_the_same_day_sends_once(self, conference, enabled):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference,
            "Read the guide",
            ItemOwner.SPEAKER,
            presenter=ada,
            due_date=days(2),
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 1
        assert send_checklist_digests(conference, now=NOW) == 0
        assert send_checklist_digests(conference, now=NOW + timedelta(hours=5)) == 0
        assert len(mail.outbox) == 1
        # The one-day threshold still fires when the day comes.
        assert send_checklist_digests(conference, now=NOW + timedelta(days=1)) == 1
        assert ReminderLog.objects.count() == 3

    def test_timezone_boundary(self, conference, enabled):
        """23:30 UTC on the 30th is already the 1st in Lagos: an item due on
        the 8th is 7 days away there (reminder) but 8 days away in UTC."""
        lagos = make_presenter(
            conference, email="lagos@example.com", timezone="Africa/Lagos"
        )
        utc = make_presenter(conference, email="utc@example.com", timezone="UTC")
        due = date(2026, 12, 8)
        add_adhoc_item(
            conference, "Slides", ItemOwner.SPEAKER, presenter=lagos, due_date=due
        )
        add_adhoc_item(
            conference, "Slides", ItemOwner.SPEAKER, presenter=utc, due_date=due
        )
        mail.outbox.clear()
        late_evening = datetime(2026, 11, 30, 23, 30, tzinfo=timezone.utc)
        assert send_checklist_digests(conference, now=late_evening) == 1
        assert mail.outbox[0].to == ["lagos@example.com"]
        assert "dates in Africa/Lagos" in mail.outbox[0].body
        assert "Tuesday 8 December" in mail.outbox[0].body
        assert (
            send_checklist_digests(conference, now=late_evening + timedelta(hours=1))
            == 1
        )
        assert mail.outbox[1].to == ["utc@example.com"]

    def test_overdue_reminded_once(self, conference, enabled):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference, "Late", ItemOwner.SPEAKER, presenter=ada, due_date=days(-4)
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 1
        assert "(overdue)" in mail.outbox[0].body
        assert send_checklist_digests(conference, now=NOW + timedelta(days=3)) == 0

    def test_nothing_due_sends_nothing(self, conference, enabled):
        make_presenter(conference)
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 0
        assert mail.outbox == []


@pytest.mark.django_db
class TestOrganizerDigest:
    def test_per_assignee_and_fallback_list(self, conference):
        make_settings(
            conference,
            organizers_email="team@example.com",
            conference_timezone="Europe/Lisbon",
        )
        lena = User.objects.create_user(username="lena", email="lena@example.com")
        ada = make_presenter(conference, display_name="Ada")
        add_adhoc_item(
            conference,
            "Promo",
            ItemOwner.ORGANIZER,
            presenter=ada,
            due_date=days(1),
            assignee=lena,
        )
        add_adhoc_item(
            conference,
            "Schedule mail",
            ItemOwner.ORGANIZER,
            presenter=ada,
            due_date=days(6),
        )
        add_adhoc_item(
            conference,
            "Nobody yet",
            ItemOwner.ORGANIZER,
            presenter=ada,
            due_date=days(2),
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 2
        by_to = {tuple(m.to): m for m in mail.outbox}
        assert "Promo" in by_to[("lena@example.com",)].body
        assert "for Ada" in by_to[("lena@example.com",)].body
        team = by_to[("team@example.com",)]
        assert "Schedule mail" in team.body and "Nobody yet" in team.body
        assert "2 organizer item(s)" in team.subject
        assert "/speakers/checklists/queue/" in team.body
        assert "dates in Europe/Lisbon" in team.body

    def test_not_yet_due_organizer_item_skipped(self, conference, enabled, admin_user):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference,
            "Far away",
            ItemOwner.ORGANIZER,
            presenter=ada,
            due_date=days(20),
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 0

    def test_fallback_to_staff_when_no_list(self, conference, enabled, admin_user):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference, "Promo", ItemOwner.ORGANIZER, presenter=ada, due_date=days(1)
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 1
        assert mail.outbox[0].to == ["admin@example.com"]

    def test_no_recipients_at_all(self, conference, enabled):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference, "Promo", ItemOwner.ORGANIZER, presenter=ada, due_date=days(1)
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 0

    def test_assignee_without_email_uses_fallback(self, conference, admin_user):
        make_settings(conference)
        ghost = User.objects.create_user(username="ghost", email="")
        add_adhoc_item(
            conference,
            "Promo",
            ItemOwner.ORGANIZER,
            presenter=make_presenter(conference),
            due_date=days(1),
            assignee=ghost,
        )
        mail.outbox.clear()
        send_checklist_digests(conference, now=NOW)
        assert mail.outbox[0].to == ["admin@example.com"]

    def test_without_settings_row_uses_utc(self, conference, admin_user):
        add_adhoc_item(
            conference,
            "Promo",
            ItemOwner.ORGANIZER,
            presenter=make_presenter(conference),
            due_date=days(1),
        )
        mail.outbox.clear()
        assert send_checklist_digests(conference, now=NOW) == 1
        assert "dates in UTC" in mail.outbox[0].body


@pytest.mark.django_db
class TestFailureIsolation:
    def test_one_failed_send_does_not_abort_the_day(self, conference, enabled):
        ada = make_presenter(conference, email="ada@example.com")
        bea = make_presenter(conference, email="bea@example.com")
        for p in (ada, bea):
            add_adhoc_item(
                conference,
                "Read",
                ItemOwner.SPEAKER,
                presenter=p,
                due_date=date.today() + timedelta(days=1),
            )
        calls = []

        def flaky(subject, recipients, **kwargs):
            calls.append(recipients)
            if len(calls) == 1:
                raise RuntimeError("smtp down")

        with mock.patch("speakers.reminders.send_email", side_effect=flaky):
            sent = send_checklist_digests(conference, now=NOW)
        assert sent == 1 and sent.failed == 1 and len(calls) == 2
        # The failed digest is not marked as sent (its rows rolled back with
        # the send), so it goes out next time; the delivered one is recorded.
        assert not ReminderLog.objects.filter(item__presenter=ada).exists()
        assert ReminderLog.objects.filter(item__presenter=bea).exists()
        with mock.patch("speakers.reminders.send_email", side_effect=flaky):
            calls.clear()
            result = send_checklist_digests_task()
        assert "(1 failed)" in result

    def test_organizer_digest_failure_is_isolated_too(self, conference, enabled):
        ada = make_presenter(conference)
        lena = User.objects.create_user(username="lena", email="lena@example.com")
        add_adhoc_item(
            conference,
            "Promo",
            ItemOwner.ORGANIZER,
            presenter=ada,
            assignee=lena,
            due_date=date.today() + timedelta(days=1),
        )
        with mock.patch(
            "speakers.reminders.send_email", side_effect=RuntimeError("smtp down")
        ):
            sent = send_checklist_digests(conference, now=NOW)
        assert sent == 0 and sent.failed == 1
        assert not ReminderLog.objects.exists()


class TestTask:
    def test_task_runs_per_enabled_edition(self, conference, enabled):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference,
            "Read",
            ItemOwner.SPEAKER,
            presenter=ada,
            due_date=date.today() + timedelta(days=1),
        )
        mail.outbox.clear()
        assert send_checklist_digests_task() == "PyLadiesCon 2025: 1 email(s)"
        assert len(mail.outbox) == 1

    def test_task_with_nothing_enabled(self, conference):
        assert (
            send_checklist_digests_task() == "No edition has the speaker module enabled"
        )

    def test_admin(self, client, admin_user, conference, enabled):
        ada = make_presenter(conference)
        add_adhoc_item(
            conference, "Read", ItemOwner.SPEAKER, presenter=ada, due_date=date.today()
        )
        send_checklist_digests(conference)
        client.force_login(admin_user)
        response = client.get(reverse("admin:speakers_reminderlog_changelist"))
        assert response.status_code == 200 and "Read" in response.content.decode()
