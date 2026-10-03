import importlib
import logging
import smtplib
from datetime import timedelta

import pytest
from celery.exceptions import Retry
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.core import mail
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from common.models import SentEmail, SentEmailStatus, prune_sent_emails
from common.workers import Worker, WorkerReport, email_code_version
from portal.models import Conference
from portal_account.permissions import MAINTAINERS_GROUP
from speakers import delivery, delivery_views
from speakers import tasks as delivery_tasks
from speakers.delivery import (
    CLOCK_SLACK,
    GONE,
    GRACE,
    RECORDS_MIGRATION,
    RETRIGGERED,
    SENT,
    WAITING,
    records_began,
    retrigger,
    retriggered_history,
    unrecorded_invitations,
)
from speakers.emails import INVITATION_TEMPLATE, invitation_email_recorded
from speakers.models import ActivityLog, Invitation
from speakers.tasks import send_invitation_email_task

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

migration = importlib.import_module("portal_account.migrations.0004_maintenance_setup")

LIST_URL = "maintenance_invitations"
SEND_URL = "maintenance_invitations_send"


@pytest.fixture(autouse=True)
def migrations_table(db):
    """Tests run without migrations, so the table that records them (which
    production always has) does not exist. Created inside the test's own
    transaction, so it is rolled back with it."""
    MigrationRecorder(connection).ensure_schema()


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """The page asks the broker which workers are attached; tests have none,
    so it answers with nobody unless a test says otherwise."""
    report = WorkerReport([], email_code_version())
    monkeypatch.setattr(delivery_views, "inspect_workers", lambda: report)
    return report


@pytest.fixture
def maintainer(db):
    """A non-staff user whose only capability is the maintainers group."""
    migration.create_maintainers_group(apps, None)
    user = User.objects.create_user(username="maintainer", email="m@example.com")
    user.groups.add(Group.objects.get(name=MAINTAINERS_GROUP))
    return user


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


def began(days=30):
    """Email records started ``days`` days ago: the moment the migration that
    creates the table was applied. Tests run without migrations, so the row
    the deploy would have left is written here."""
    row, _ = MigrationRecorder.Migration.objects.get_or_create(
        app="common", name="0001_sent_email"
    )
    MigrationRecorder.Migration.objects.filter(pk=row.pk).update(
        applied=timezone.now() - timedelta(days=days)
    )


def sent_invitation(conference, name, *, minutes_ago=60, **stamps):
    """An invitation marked sent ``minutes_ago`` minutes ago, as the web does."""
    session = make_session(conference, kind="WORKSHOP", title=f"Talk by {name}")
    presenter = make_presenter(
        conference, display_name=name, email=f"{name.lower()}@example.com"
    )
    add_presenter(session, presenter)
    invitation = make_invitation(presenter, session, **stamps)
    invitation.issue_token(now=timezone.now() - timedelta(minutes=minutes_ago))
    invitation.save()
    return invitation


def record(invitation, status=SentEmailStatus.SENT, *, error="", after=None):
    """The sent-email row the worker writes for an invitation."""
    return SentEmail.objects.create(
        conference=invitation.conference,
        to=invitation.sent_to,
        subject="You're invited",
        template=INVITATION_TEMPLATE,
        context_digest={"invitation": invitation.pk},
        sent_at=after or invitation.sent_at + timedelta(seconds=5),
        status=status,
        error=error,
    )


def unrecorded(conference):
    return {item.invitation.pk: item for item in unrecorded_invitations(conference)}


@pytest.mark.django_db
class TestRecordsBegan:
    def test_is_none_when_the_migration_is_not_recorded(self):
        assert records_began() is None

    def test_is_when_the_migration_was_applied(self):
        began(days=10)
        age = timezone.now() - records_began()
        assert abs(age - timedelta(days=10)) < timedelta(minutes=1)

    def test_the_migration_it_reads_exists(self):
        """Squashing or renaming it would leave the page blind."""
        app, name = RECORDS_MIGRATION
        importlib.import_module(f"{app}.migrations.{name}")

    def test_two_migration_rows_give_the_earliest(self):
        began(days=5)
        MigrationRecorder.Migration.objects.create(
            app="common",
            name="0001_sent_email",
            applied=timezone.now() - timedelta(days=50),
        )
        age = timezone.now() - records_began()
        assert abs(age - timedelta(days=50)) < timedelta(minutes=1)

    def test_does_not_depend_on_which_email_rows_survive(self, conference, enabled):
        began(days=100)
        before = records_began()
        SentEmail.objects.create(
            to="x@example.com",
            subject="Latest",
            template="emails/other.md",
            sent_at=timezone.now(),
        )
        assert records_began() == before


@pytest.mark.django_db
class TestUnrecordedInvitations:
    def test_nothing_to_compare_with_when_the_start_is_unknown(
        self, conference, enabled
    ):
        sent_invitation(conference, "Ada")
        assert unrecorded_invitations(conference) == []

    def test_a_recorded_invitation_is_not_listed(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation)
        assert unrecorded(conference) == {}

    def test_an_invitation_without_a_record_is_listed(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        item = unrecorded(conference)[invitation.pk]
        assert item.failure == ""
        assert item.in_flight is False

    def test_first_sends_lost_with_a_later_record_are_still_listed(
        self, conference, enabled
    ):
        """The lost sends are older than every row that exists. Inferring the
        start from the oldest row would hide all three."""
        began(days=30)
        lost = [sent_invitation(conference, n, minutes_ago=120) for n in "ABC"]
        record(sent_invitation(conference, "Later", minutes_ago=10))
        assert set(unrecorded(conference)) == {i.pk for i in lost}

    def test_the_prune_does_not_hide_one(self, conference, enabled):
        began(days=100)
        invitation = sent_invitation(conference, "Ada")
        SentEmail.objects.create(
            to="old@example.com",
            subject="Old",
            template="emails/other.md",
            sent_at=timezone.now() - timedelta(days=500),
        )
        assert invitation.pk in unrecorded(conference)
        assert prune_sent_emails() == 1
        assert invitation.pk in unrecorded(conference)

    def test_oldest_first(self, conference, enabled):
        began()
        newer = sent_invitation(conference, "Newer", minutes_ago=30)
        older = sent_invitation(conference, "Older", minutes_ago=90)
        listed = [i.invitation.pk for i in unrecorded_invitations(conference)]
        assert listed == [older.pk, newer.pk]

    def test_only_limits_it_to_one(self, conference, enabled):
        began()
        sent_invitation(conference, "Ada")
        grace = sent_invitation(conference, "Grace")
        listed = unrecorded_invitations(conference, only=grace.pk)
        assert [i.invitation.pk for i in listed] == [grace.pk]

    def test_a_failed_record_is_listed_with_its_error(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="SMTPRecipientsRefused: no")
        item = unrecorded(conference)[invitation.pk]
        assert item.failure == "SMTPRecipientsRefused: no"
        assert item.in_flight is False

    def test_the_latest_failure_is_the_one_shown(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="first")
        record(
            invitation,
            SentEmailStatus.FAILED,
            error="second",
            after=invitation.sent_at + timedelta(minutes=2),
        )
        assert unrecorded(conference)[invitation.pk].failure == "second"

    def test_a_failure_then_a_success_is_recorded(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="first")
        record(invitation, after=invitation.sent_at + timedelta(minutes=2))
        assert unrecorded(conference) == {}

    def test_a_record_from_an_earlier_send_does_not_count(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, after=invitation.sent_at - CLOCK_SLACK * 3)
        assert invitation.pk in unrecorded(conference)

    def test_a_record_a_second_before_the_stamp_counts(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, after=invitation.sent_at - timedelta(seconds=1))
        assert unrecorded(conference) == {}

    def test_a_recent_send_is_in_flight(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada", minutes_ago=1)
        assert unrecorded(conference)[invitation.pk].in_flight is True

    def test_a_recent_failure_is_not_in_flight(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada", minutes_ago=1)
        record(invitation, SentEmailStatus.FAILED, error="refused")
        assert unrecorded(conference)[invitation.pk].in_flight is False

    def test_an_answered_or_opened_invitation_is_not_listed(self, conference, enabled):
        began()
        now = timezone.now()
        for name, field in (
            ("Opened", "opened_at"),
            ("Accepted", "accepted_at"),
            ("Declined", "declined_at"),
            ("Cancelled", "cancelled_at"),
        ):
            invitation = sent_invitation(conference, name)
            setattr(invitation, field, now)
            invitation.save()
        assert unrecorded(conference) == {}

    def test_an_invitation_never_sent_is_not_listed(self, conference, enabled):
        began()
        session = make_session(conference, kind="WORKSHOP", title="Draft")
        presenter = make_presenter(conference, display_name="Draft", email="d@x.org")
        make_invitation(presenter, session)
        assert unrecorded(conference) == {}

    def test_one_sent_before_records_began_is_not_judged(self, conference, enabled):
        began(days=30)
        invitation = sent_invitation(conference, "Ada", minutes_ago=60 * 24 * 40)
        assert invitation.pk not in unrecorded(conference)

    def test_an_expired_invitation_is_listed(self, conference, enabled):
        began(days=60)
        invitation = sent_invitation(conference, "Ada", minutes_ago=60 * 24 * 20)
        assert unrecorded(conference)[invitation.pk].invitation.status == "EXPIRED"


@pytest.mark.django_db
class TestRetrigger:
    def test_sends_the_invitation_and_it_leaves_the_list(
        self, conference, enabled, maintainer, django_capture_on_commit_callbacks
    ):
        began()
        invitation = sent_invitation(conference, "Ada")
        old_token, old_sent_at = invitation.token, invitation.sent_at
        with django_capture_on_commit_callbacks(execute=True):
            outcome, sent = retrigger(conference, invitation.pk, actor=maintainer)
        assert (outcome, sent.pk) == (SENT, invitation.pk)
        invitation.refresh_from_db()
        assert invitation.token != old_token
        assert invitation.sent_at > old_sent_at
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]
        assert SentEmail.objects.filter(
            template=INVITATION_TEMPLATE, status=SentEmailStatus.SENT
        ).exists()
        assert unrecorded(conference) == {}

    def test_logs_who_did_it_and_what_it_replaced(
        self, conference, enabled, maintainer, django_capture_on_commit_callbacks
    ):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="refused")
        with django_capture_on_commit_callbacks(execute=True):
            retrigger(conference, invitation.pk, actor=maintainer)
        entry = ActivityLog.objects.get(action=RETRIGGERED)
        assert entry.actor == maintainer
        assert entry.target == invitation
        assert entry.data["failure"] == "refused"
        assert "no email record" in entry.message
        assert retriggered_history(conference) == [entry]

    def test_writes_a_log_line(
        self,
        conference,
        enabled,
        maintainer,
        caplog,
        django_capture_on_commit_callbacks,
    ):
        began()
        plain = sent_invitation(conference, "Ada")
        failed = sent_invitation(conference, "Grace")
        record(failed, SentEmailStatus.FAILED, error="refused")
        with caplog.at_level(logging.INFO, logger="speakers"):
            with django_capture_on_commit_callbacks(execute=True):
                retrigger(conference, plain.pk, actor=maintainer)
                retrigger(conference, failed.pk, actor=maintainer)
        assert f"Retriggered invitation {plain.pk}" in caplog.text
        assert "(failed: refused)" in caplog.text
        assert "Invitation email: sending invitation" in caplog.text

    def test_sends_only_the_one_asked_for(
        self, conference, enabled, maintainer, django_capture_on_commit_callbacks
    ):
        began()
        ticked = sent_invitation(conference, "Ada")
        other = sent_invitation(conference, "Grace")
        with django_capture_on_commit_callbacks(execute=True):
            retrigger(conference, ticked.pk, actor=maintainer)
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]
        assert other.pk in unrecorded(conference)

    def test_one_that_is_recorded_is_gone(self, conference, enabled, maintainer):
        began()
        recorded = sent_invitation(conference, "Ada")
        record(recorded)
        assert retrigger(conference, recorded.pk, actor=maintainer) == (GONE, None)
        assert mail.outbox == []

    def test_one_that_does_not_exist_is_gone(self, conference, enabled, maintainer):
        began()
        assert retrigger(conference, 99999, actor=maintainer) == (GONE, None)

    def test_one_of_another_edition_is_gone(self, conference, enabled, maintainer):
        began()
        invitation = sent_invitation(conference, "Ada")
        other = Conference.objects.create(
            year=conference.year - 1, name="Earlier", is_active=False
        )
        assert retrigger(other, invitation.pk, actor=maintainer) == (GONE, None)

    def test_one_that_may_still_be_on_its_way_waits(
        self, conference, enabled, maintainer
    ):
        began()
        invitation = sent_invitation(conference, "Ada", minutes_ago=1)
        before = invitation.token
        outcome, found = retrigger(conference, invitation.pk, actor=maintainer)
        assert (outcome, found.pk) == (WAITING, invitation.pk)
        invitation.refresh_from_db()
        assert invitation.token == before

    def test_a_second_click_waits_for_the_first(
        self, conference, enabled, maintainer, django_capture_on_commit_callbacks
    ):
        """The row is re-stamped by the first send, so the second finds it
        in flight and does not issue another link."""
        began()
        invitation = sent_invitation(conference, "Ada")
        with django_capture_on_commit_callbacks(execute=False):
            first = retrigger(conference, invitation.pk, actor=maintainer)
            second = retrigger(conference, invitation.pk, actor=maintainer)
        assert (first[0], second[0]) == (SENT, WAITING)
        assert ActivityLog.objects.filter(action=RETRIGGERED).count() == 1

    def test_one_accepted_in_the_meantime_is_gone(
        self, conference, enabled, maintainer, monkeypatch
    ):
        began()
        invitation = sent_invitation(conference, "Ada")

        def accepted(invitation, actor=None):
            Invitation.objects.filter(pk=invitation.pk).update(
                accepted_at=timezone.now()
            )
            raise ValueError("This invitation has already been accepted.")

        monkeypatch.setattr(delivery, "send_invitation", accepted)
        assert retrigger(conference, invitation.pk, actor=maintainer) == (GONE, None)
        assert not ActivityLog.objects.filter(action=RETRIGGERED).exists()

    def test_any_other_value_error_is_not_hidden_as_gone(
        self, conference, enabled, maintainer, monkeypatch
    ):
        began()
        invitation = sent_invitation(conference, "Ada")

        def broken(invitation, actor=None):
            raise ValueError("something else is wrong")

        monkeypatch.setattr(delivery, "send_invitation", broken)
        with pytest.raises(ValueError, match="something else is wrong"):
            retrigger(conference, invitation.pk, actor=maintainer)

    def test_grace_is_a_few_minutes(self):
        assert timedelta(minutes=1) < GRACE <= timedelta(minutes=15)


@pytest.mark.django_db
class TestInvitationTaskLogging:
    def test_logs_start_and_end_with_the_task_id(self, conference, enabled, caplog):
        invitation = sent_invitation(conference, "Ada")
        with caplog.at_level(logging.INFO, logger="speakers"):
            send_invitation_email_task.apply(args=[invitation.pk], task_id="abc-123")
        assert f"sending invitation {invitation.pk} to presenter" in caplog.text
        assert "(task abc-123)" in caplog.text
        assert "sent, email record" in caplog.text
        assert "ada@example.com" not in caplog.text

    def test_a_missing_invitation_is_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="speakers"):
            result = send_invitation_email_task.apply(args=[424242]).get()
        assert "424242 not found" in caplog.text
        assert "not found" in result

    def test_a_failure_is_logged_and_raised(
        self, conference, enabled, monkeypatch, caplog
    ):
        invitation = sent_invitation(conference, "Ada")

        def boom(_):
            raise RuntimeError("smtp down")

        monkeypatch.setattr("speakers.tasks.send_invitation_email", boom)
        with caplog.at_level(logging.ERROR, logger="speakers"):
            with pytest.raises(RuntimeError, match="smtp down"):
                send_invitation_email_task.apply(args=[invitation.pk])
        assert f"invitation {invitation.pk} failed" in caplog.text
        assert "smtp down" in caplog.text


@pytest.mark.django_db
class TestRedeliveredInvitationTask:
    """The task is acknowledged late, so a worker that dies holding it gets it
    back; it must not mail the presenter a second time."""

    def test_one_already_on_record_is_not_sent_again(self, conference, enabled, caplog):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation)
        with caplog.at_level(logging.INFO, logger="speakers"):
            result = send_invitation_email_task.apply(args=[invitation.pk]).get()
        assert result == f"Invitation email for {invitation.pk} was already sent"
        assert "already has a successful record" in caplog.text
        assert mail.outbox == []

    def test_a_record_of_an_earlier_send_does_not_stop_a_new_one(
        self, conference, enabled
    ):
        """A resend issues a new link; the old record is not this send."""
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, after=invitation.sent_at - timedelta(minutes=30))
        send_invitation_email_task.apply(args=[invitation.pk]).get()
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]

    def test_a_resend_within_a_minute_of_the_last_send_still_goes_out(
        self, conference, enabled
    ):
        """The audit page forgives a minute of clock skew; this must not, or a
        quick resend finds the previous send's record and is skipped."""
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, after=invitation.sent_at - timedelta(seconds=30))
        send_invitation_email_task.apply(args=[invitation.pk]).get()
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]

    def test_a_failed_record_does_not_stop_it(self, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="down")
        send_invitation_email_task.apply(args=[invitation.pk]).get()
        assert len(mail.outbox) == 1

    def test_a_draft_invitation_is_not_on_record(self, conference, enabled):
        session = make_session(conference, kind="WORKSHOP", title="Draft")
        presenter = make_presenter(conference, display_name="Dee", email="dee@x.org")
        draft = make_invitation(presenter, session)
        assert draft.sent_at is None
        assert invitation_email_recorded(draft) is False

    def test_a_down_mail_server_is_tried_again_and_mailed_once(
        self, conference, enabled, monkeypatch
    ):
        invitation = sent_invitation(conference, "Ada")
        real = delivery_tasks.send_invitation_email
        calls = []

        def flaky(inv):
            calls.append(inv.pk)
            if len(calls) == 1:
                raise ConnectionError("mail server unreachable")
            return real(inv)

        monkeypatch.setattr(delivery_tasks, "send_invitation_email", flaky)
        with pytest.raises(Retry):
            send_invitation_email_task.apply(args=[invitation.pk])
        assert mail.outbox == []
        send_invitation_email_task.apply(args=[invitation.pk], retries=1).get()
        assert len(calls) == 2
        assert len(mail.outbox) == 1

    def test_a_refused_address_is_not_tried_again(
        self, conference, enabled, monkeypatch
    ):
        invitation = sent_invitation(conference, "Ada")
        calls = []

        def refused(inv):
            calls.append(inv.pk)
            raise smtplib.SMTPRecipientsRefused({"a@x.org": (550, b"no")})

        monkeypatch.setattr(delivery_tasks, "send_invitation_email", refused)
        with pytest.raises(smtplib.SMTPRecipientsRefused):
            send_invitation_email_task.apply(args=[invitation.pk])
        assert len(calls) == 1


@pytest.mark.django_db
class TestMaintenanceInvitationsPage:
    def login(self, client, user):
        client.force_login(user)
        return client

    def test_anonymous_is_sent_to_sign_in(self, client):
        response = client.get(reverse(LIST_URL))
        assert response.status_code == 302
        assert "login" in response.url

    def test_a_non_maintainer_is_refused(self, client, portal_user):
        self.login(client, portal_user)
        assert client.get(reverse(LIST_URL)).status_code == 403
        assert client.post(reverse(SEND_URL), {"invitation": "1"}).status_code == 403

    def test_lists_the_mismatch_with_a_button_per_row(
        self, client, maintainer, conference, enabled
    ):
        began()
        missing = sent_invitation(conference, "Ada")
        recorded = sent_invitation(conference, "Grace")
        record(recorded)
        failed = sent_invitation(conference, "Edsger")
        record(failed, SentEmailStatus.FAILED, error="SMTPRecipientsRefused: no")
        sent_invitation(conference, "Recent", minutes_ago=1)
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "Ada")
        assertContains(response, "No record")
        assertContains(response, "SMTPRecipientsRefused: no")
        assertContains(response, "Probably still queued")
        assertContains(response, f'name="invitation" value="{missing.pk}"')
        assertContains(response, "Wait", count=1, html=False)
        assertNotContains(response, "Grace")
        assertNotContains(response, "Send all")
        assertNotContains(response, "checkbox")

    def test_a_long_error_is_cut(self, client, maintainer, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada")
        record(invitation, SentEmailStatus.FAILED, error="x" * 1500)
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertNotContains(response, "x" * 300)

    def test_says_when_everything_is_recorded(
        self, client, maintainer, conference, enabled
    ):
        began()
        record(sent_invitation(conference, "Ada"))
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "Every invitation marked sent has an email record.")
        assertNotContains(response, "Send again</button>")

    def test_says_when_the_start_of_records_is_unknown(
        self, client, maintainer, conference
    ):
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "nothing to compare with")

    def test_says_when_there_is_no_active_edition(self, client, maintainer, conference):
        Conference.objects.update(is_active=False)
        client = self.login(client, maintainer)
        assertContains(client.get(reverse(LIST_URL)), "no active edition")
        response = client.post(reverse(SEND_URL), {"invitation": "1"}, follow=True)
        assertContains(response, "There is no active edition.")

    def test_get_is_not_allowed_on_the_send_url(self, client, maintainer):
        assert self.login(client, maintainer).get(reverse(SEND_URL)).status_code == 405

    def test_sends_the_one_invitation(self, client, maintainer, conference, enabled):
        began()
        ticked = sent_invitation(conference, "Ada")
        sent_invitation(conference, "Grace")
        response = self.login(client, maintainer).post(
            reverse(SEND_URL), {"invitation": str(ticked.pk)}, follow=True
        )
        assertContains(response, "Sent again to Ada.")
        assertContains(response, "Sent again from Maintenance")
        assertContains(response, "Grace")
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]

    def test_one_just_sent_waits(self, client, maintainer, conference, enabled):
        began()
        invitation = sent_invitation(conference, "Ada", minutes_ago=1)
        response = self.login(client, maintainer).post(
            reverse(SEND_URL), {"invitation": str(invitation.pk)}, follow=True
        )
        assertContains(response, "Ada was sent an email in the last 5 minutes")
        assertContains(response, "Wait for it to be recorded")
        assert mail.outbox == []

    def test_one_no_longer_on_the_list_says_so(
        self, client, maintainer, conference, enabled
    ):
        began()
        recorded = sent_invitation(conference, "Ada")
        record(recorded)
        client = self.login(client, maintainer)
        for value in (str(recorded.pk), "99999"):
            response = client.post(
                reverse(SEND_URL), {"invitation": value}, follow=True
            )
            assertContains(response, "no longer on the list")
        assert mail.outbox == []

    def test_choosing_nothing_is_an_error(self, client, maintainer, conference):
        client = self.login(client, maintainer)
        for data in ({}, {"invitation": "x"}, {"all": "1"}):
            response = client.post(reverse(SEND_URL), data, follow=True)
            assertContains(response, "Choose an invitation to send again.")

    def test_history_is_shown_newest_first(
        self, client, maintainer, conference, enabled
    ):
        began()
        for text in ("older entry", "newer entry"):
            ActivityLog.record(
                conference, RETRIGGERED, actor=maintainer, message=text, failure=""
            )
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        body = response.content.decode()
        assert body.index("newer entry") < body.index("older entry")


@pytest.mark.django_db
class TestWorkersPanel:
    def login(self, client, user):
        client.force_login(user)
        return client

    def show(self, monkeypatch, workers, error="", problems=None):
        report = WorkerReport(
            workers, email_code_version(), problems or [], error=error
        )
        monkeypatch.setattr(delivery_views, "inspect_workers", lambda: report)

    def worker(self, name, queues=("celery",), code="current", version=None, error=""):
        return Worker(
            name=f"celery@{name}",
            queues=queues,
            uptime=7200,
            started=timezone.now() - timedelta(hours=2),
            tasks={"speakers.tasks.send_invitation_email_task": 3},
            code=code,
            version=(
                email_code_version()
                if version is None and code == "current"
                else (version or "")
            ),
            error=error,
        )

    def test_lists_each_worker_with_its_code(
        self, client, maintainer, monkeypatch, conference
    ):
        self.show(
            monkeypatch,
            [
                self.worker("new-1"),
                self.worker("old-2", code="older"),
                self.worker("other-3", code="differs", version="deadbeef"),
                self.worker("bad-4", code="error", error="RuntimeError('boom')"),
                self.worker("mute-5", code="silent"),
                self.worker("media-6", queues=("media",)),
                self.worker("dev-7", queues=("celery", "media")),
            ],
            problems=["Two workers read the default queue."],
        )
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "Workers")
        assertContains(response, "new-1")
        assertContains(response, 'text-bg-success">same as this site', count=3)
        assertContains(response, 'text-bg-danger">not reported', count=1)
        assertContains(response, 'text-bg-warning">differs', count=1)
        assertContains(response, 'text-bg-danger">error', count=1)
        assertContains(response, 'text-bg-warning">no answer', count=1)
        assertContains(response, "RuntimeError(&#x27;boom&#x27;)")
        assertContains(response, "deadbeef")
        assertContains(response, "default and media")
        assertContains(response, "2\xa0hours ago")
        assertContains(response, "Two workers read the default queue.")
        assertContains(response, email_code_version())

    def test_no_problems_means_no_alert(
        self, client, maintainer, monkeypatch, conference
    ):
        self.show(monkeypatch, [self.worker("only")])
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "only")
        assertNotContains(response, "alert-danger")

    def test_says_when_nobody_answers(
        self, client, maintainer, monkeypatch, conference
    ):
        self.show(monkeypatch, [], problems=["No worker is reading the default queue."])
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "No worker answered.")
        assertContains(response, "No worker is reading the default queue.")

    def test_says_when_the_broker_cannot_be_asked(
        self, client, maintainer, monkeypatch, conference
    ):
        self.show(monkeypatch, [], error="ConnectionError: refused")
        response = self.login(client, maintainer).get(reverse(LIST_URL))
        assertContains(response, "could not be asked which workers are attached")
        assertContains(response, "ConnectionError: refused")
        assertNotContains(response, "No worker answered.")
