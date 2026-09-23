from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core import mail

from speakers.checklists import add_adhoc_item
from speakers.constants import ItemOwner, NoticeKind
from speakers.models import ChecklistItem
from speakers.notices import send_checklist_change_notices
from speakers.tasks import send_checklist_change_notices_task
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.mark.django_db
class TestChangeNotices:
    def test_one_email_per_recipient_then_silence(self, conference, enabled):
        ada = make_presenter(conference, display_name="Ada", email="ada@example.com")
        session = make_session(conference, title="Django 101")
        add_presenter(session, ada)
        add_adhoc_item(
            conference,
            "Bring cookies",
            ItemOwner.SPEAKER,
            presenter=ada,
            session=session,
            due_date=date(2026, 12, 1),
        )
        changed = add_adhoc_item(
            conference, "Send slides", ItemOwner.SPEAKER, presenter=ada
        )
        ChecklistItem.objects.filter(pk=changed.pk).update(
            pending_notice=NoticeKind.CHANGED
        )
        lena = User.objects.create_user(username="lena", email="lena@example.com")
        add_adhoc_item(
            conference, "Promo", ItemOwner.ORGANIZER, presenter=ada, assignee=lena
        )
        add_adhoc_item(conference, "Nobody's", ItemOwner.ORGANIZER, presenter=ada)
        mail.outbox.clear()
        assert send_checklist_change_notices(conference) == 2
        by_to = {tuple(m.to): m for m in mail.outbox}
        speaker_mail = by_to[("ada@example.com",)]
        assert speaker_mail.subject.endswith(
            "PyLadiesCon 2025: Update to your todo list"
        )
        assert "Thank you for being a speaker at PyLadiesCon 2025" in speaker_mail.body
        assert (
            "Your session:" in speaker_mail.body
            and "not scheduled yet" in speaker_mail.body
        )
        assert "visit your speaker dashboard" in speaker_mail.body
        assert "\nNew\n" in speaker_mail.body and "Bring cookies" in speaker_mail.body
        assert "<h2>New</h2>" in speaker_mail.alternatives[0][0]
        assert (
            "Django 101" in speaker_mail.body
            and "Tuesday 1 December" in speaker_mail.body
        )
        assert "\nChanged\n" in speaker_mail.body and "Send slides" in speaker_mail.body
        assert "/speakers/me/" in speaker_mail.body
        organizer_mail = by_to[("lena@example.com",)]
        assert organizer_mail.subject.endswith("Update to your team todo list")
        assert "Promo" in organizer_mail.body and "for Ada" in organizer_mail.body
        assert "Thank you for being" not in organizer_mail.body
        assert (
            "Thank you for volunteering with us at PyLadiesCon 2025"
            in organizer_mail.body
        )
        assert "Go to your queue for more details" in organizer_mail.body
        for message in (speaker_mail, organizer_mail):
            assert "mark them as done and we won't bother you" in message.body
        assert "/speakers/checklists/queue/" in organizer_mail.body
        assert not ChecklistItem.objects.exclude(pending_notice="").exists()
        mail.outbox.clear()
        assert send_checklist_change_notices(conference) == 0
        assert mail.outbox == []

    def test_team_items_go_to_approved_members(self, conference, enabled):
        team = Team.objects.create(
            conference=conference, short_name="Design", description="d"
        )
        for name, status in (
            ("kim", ApplicationStatus.APPROVED),
            ("mia", ApplicationStatus.PENDING),
        ):
            user = User.objects.create_user(username=name, email=f"{name}@example.com")
            VolunteerProfile.objects.create(
                user=user, conference=conference, application_status=status
            ).teams.add(team)
        add_adhoc_item(
            conference,
            "Poster",
            ItemOwner.ORGANIZER,
            presenter=make_presenter(conference),
            team=team,
        )
        mail.outbox.clear()
        assert send_checklist_change_notices(conference) == 1
        assert mail.outbox[0].to == ["kim@example.com"]

    def test_task(self, conference, enabled):
        add_adhoc_item(
            conference, "x", ItemOwner.SPEAKER, presenter=make_presenter(conference)
        )
        mail.outbox.clear()
        assert send_checklist_change_notices_task() == "PyLadiesCon 2025: 1 email(s)"
        enabled.speaker_module_enabled = False
        enabled.save()
        assert (
            send_checklist_change_notices_task()
            == "No edition has the speaker module enabled"
        )

    def test_one_bad_mailbox_does_not_silence_the_rest(
        self, conference, enabled, monkeypatch
    ):
        """The rule the reminder digests already follow: log it, count it,
        carry on, and leave the failed recipient's flags for tomorrow."""
        first = make_presenter(conference, display_name="Ada", email="ada@example.com")
        second = make_presenter(conference, display_name="Bea", email="bea@example.com")
        for presenter in (first, second):
            add_adhoc_item(
                conference, "Send your slides", ItemOwner.SPEAKER, presenter=presenter
            )
        sent = []
        real = mail.get_connection

        def explode_for_ada(subject, recipients, **kwargs):
            if "ada@example.com" in recipients:
                raise OSError("mailbox full")
            sent.append(recipients)

        monkeypatch.setattr("speakers.notices.send_email", explode_for_ada)
        result = send_checklist_change_notices(conference)
        assert result == 1 and result.failed == 1
        assert sent == [["bea@example.com"]]
        # Ada keeps her flag, so tomorrow tries again; Bea's is cleared.
        assert (
            ChecklistItem.objects.filter(presenter=first)
            .exclude(pending_notice="")
            .exists()
        )
        assert (
            not ChecklistItem.objects.filter(presenter=second)
            .exclude(pending_notice="")
            .exists()
        )
        assert real is mail.get_connection

    def test_the_task_reports_failures(self, conference, enabled, monkeypatch):
        make_presenter(conference, display_name="Ada", email="ada@example.com")
        add_adhoc_item(
            conference,
            "Send your slides",
            ItemOwner.SPEAKER,
            presenter=make_presenter(conference, email="cleo@example.com"),
        )

        def explode(*args, **kwargs):
            raise OSError("the mail server is down")

        monkeypatch.setattr("speakers.notices.send_email", explode)
        assert "(1 failed)" in send_checklist_change_notices_task()
