"""The record of every email the portal sent (design §13.1, task 2.23)."""

import importlib
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.apps import apps
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from common.models import SentEmail, SentEmailStatus, kind_of, prune_sent_emails
from common.send_emails import (
    WITHHELD,
    register_credential_pattern,
    send_email,
    withhold_credentials,
)
from common.tasks import prune_email_records_task
from portal.models import Conference
from speakers.emails import (
    INVITATION_TEMPLATE,
    invitation_context,
    invitation_url,
    send_invitation_email,
    signed_invitation_token,
)
from speakers.models import Presenter
from tests.speakers.factories import (
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)
from volunteer.models import VolunteerProfile

migration = importlib.import_module("common.migrations.0001_sent_email")

TEMPLATE = "emails/base_email.md"


@pytest.fixture
def ada(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, ada):
    make_settings(conference)
    return make_presenter(conference, email="ada@example.com", user=ada)


def send(to, context=None, **kwargs):
    return send_email(
        "Hello", to, markdown_template=TEMPLATE, context=context, **kwargs
    )


@pytest.mark.django_db
class TestRecording:
    def test_records_what_was_sent(self):
        record = send(["someone@example.com"])
        assert len(mail.outbox) == 1
        assert record.to == "someone@example.com"
        assert record.subject == "Hello"
        assert record.template == TEMPLATE
        assert "Hello from" in record.body_md
        # Shown as the HTML part was, through the same sanitizing renderer.
        assert "<strong>" in record.body_html and "**" not in record.body_html
        assert record.status == SentEmailStatus.SENT and record.error == ""
        assert record.context_digest == {}
        assert record.kind == "base_email"
        assert str(record) == "Hello -> someone@example.com"
        assert not record.failed

    def test_presenter_email_is_theirs(self, conference, presenter):
        session = make_session(conference)
        record = send(
            [presenter.email],
            {"presenter": presenter, "session": session, "conference": conference},
        )
        assert record.presenter == presenter
        assert record.session == session
        assert record.conference == conference
        # The context carried no account; ownership still reaches Ada
        # through the presenter row (see TestOwnership).
        assert record.user is None
        assert record.context_digest == {
            "presenter": presenter.pk,
            "session": session.pk,
        }

    def test_organizer_copy_is_about_them_and_not_theirs(self, conference, presenter):
        """The organizers' notice about a proposal names the proposer in its
        context; it must never land in the proposer's own trail."""
        record = send(
            ["org@example.com"], {"presenter": presenter, "conference": conference}
        )
        assert record.presenter is None and record.user is None
        assert record.context_digest == {"presenter": presenter.pk}
        assert record.conference == conference

    def test_account_from_the_context(self, ada):
        assert send([ada.email], {"user": ada}).user == ada
        # A volunteer email carries the profile, which carries the account
        # and the edition.
        profile = VolunteerProfile.objects.create(
            user=ada, conference=Conference.get_active()
        )
        record = send([ada.email], {"profile": profile})
        assert record.user == ada
        assert record.conference == profile.conference
        assert record.context_digest == {"profile": profile.pk}

    def test_verified_address_is_the_account_s(self, ada):
        """An assignee's digest carries items in its context, not the
        assignee; an address allauth verified for exactly one active account
        is that account's."""
        assert send([ada.email], {}).user is None
        EmailAddress.objects.create(user=ada, email=ada.email, verified=True)
        assert send([ada.email], {}).user == ada
        assert send([ada.email, "x@example.com"], {}).user is None
        # An inactive account is nobody's. (allauth keeps a verified address
        # unique, so two accounts for one address cannot happen.)
        ada.is_active = False
        ada.save()
        assert send([ada.email], {}).user is None

    def test_unverified_address_proves_nothing(self, ada):
        EmailAddress.objects.create(user=ada, email=ada.email, verified=False)
        assert send([ada.email], {}).user is None

    def test_long_recipient_lists_are_kept_whole(self):
        team = [f"member{i}@example.com" for i in range(40)]
        record = send(team)
        assert record.to.split(", ") == team

    def test_address_must_match_exactly_one_recipient(self, ada, presenter):
        assert send(["other@example.com"], {"user": ada}).user is None
        assert (
            send([presenter.email, "x@example.com"], {"presenter": presenter}).presenter
            is None
        )
        # Case and whitespace are not a different address.
        assert send([" ADA@example.com "], {"user": ada}).user == ada

    def test_explicit_arguments_win(self, conference, presenter, ada):
        session = make_session(conference)
        record = send(
            ["org@example.com"],
            {},
            conference=conference,
            user=ada,
            presenter=presenter,
            session=session,
        )
        assert (record.conference, record.user, record.presenter, record.session) == (
            conference,
            ada,
            presenter,
            session,
        )

    def test_edition_read_from_what_it_is_about(self, conference, presenter):
        session = make_session(conference)
        assert send(["x@example.com"], {"session": session}).conference == conference
        assert (
            send([presenter.email], {"presenter": presenter}).conference == conference
        )
        assert send(["x@example.com"], {}).conference is None

    def test_unsaved_and_foreign_objects_are_ignored(self, conference, ada):
        draft = Presenter(conference=conference, display_name="Draft", email="d@x.org")
        record = send(
            ["d@x.org"], {"presenter": draft, "session": "nope", "conference": ada}
        )
        assert record.presenter is None and record.session is None
        assert record.conference is None
        assert record.context_digest == {}

    def test_empty_addresses_are_dropped(self, ada):
        record = send(["", ada.email], {"user": ada})
        assert record.to == ada.email and record.user == ada

    def test_secrets_go_out_and_are_withheld_from_the_record(self):
        record = send(["a@x.org"], secrets=["Hello from", ""])
        assert "Hello from" in mail.outbox[0].body
        assert "Hello from" not in record.body_md and WITHHELD in record.body_md

    def test_invitation_accept_link_is_withheld(self, conference, presenter):
        """Opening the accept link signs its reader in as the presenter
        (``InvitationView.post``), so the trail must not hold it."""
        invitation = make_invitation(presenter)
        invitation.issue_token()
        invitation.save()
        send_invitation_email(invitation)
        token = signed_invitation_token(invitation)
        assert token in mail.outbox[0].body
        record = SentEmail.objects.get()
        assert token not in record.body_md and WITHHELD in record.body_md
        assert record.presenter == presenter
        assert record.context_digest["invitation"] == invitation.pk

    def test_invitation_link_is_withheld_by_shape_when_the_sender_forgets(
        self, conference, presenter
    ):
        """A worker on yesterday's code, or a new caller that passes no
        ``secrets``, still cannot store the link: ``speakers.apps`` registers
        its shape, and every body is scrubbed against it."""
        invitation = make_invitation(presenter)
        invitation.issue_token()
        invitation.save()
        url = invitation_url(invitation)
        record = send_email(
            "Invite",
            [presenter.email],
            markdown_template=INVITATION_TEMPLATE,
            context=invitation_context(
                invitation,
                conference=conference,
                accept_url=url,
                expires_at=invitation.expires_at,
            ),
        )
        assert url in mail.outbox[0].body
        assert (
            url not in record.body_md and "/speakers/invitations/" not in record.body_md
        )
        assert WITHHELD in record.body_md

    def test_withheld_link_is_a_sentence_not_a_link(self, conference, presenter):
        invitation = make_invitation(presenter)
        invitation.issue_token()
        invitation.save()
        send_invitation_email(invitation)
        record = SentEmail.objects.get()
        assert "Accept or decline the invitation " + WITHHELD in record.body_md
        assert "](" + WITHHELD not in record.body_md
        assert 'href="[link withheld' not in record.body_html
        assert "Accept or decline the invitation" in record.body_html

    def test_body_html_keeps_no_image_source(self):
        record = SentEmail(
            body_md='Hi ![tracker](https://evil.example/px.png) and <img src="https://evil.example/md.png" alt="x">'
        )
        html = record.body_html
        assert "evil.example" not in html and "<img" in html and 'alt="x"' in html

    def test_credential_shapes_are_registered_once_and_scrub_every_form(self):
        register_credential_pattern(
            r"https?://[^\s<>()\[\]]+/speakers/invitations/[^\s<>()\[\]]+"
        )
        text = (
            '[Go](https://x.org/speakers/invitations/abc:1/ "titled") and '
            "[Accept](https://x.org/speakers/invitations/abc:1/) or "
            "<https://x.org/speakers/invitations/abc:1/> or "
            "https://x.org/speakers/invitations/abc:1/ but not https://x.org/speakers/me/"
        )
        scrubbed = withhold_credentials(text)
        assert "invitations/abc" not in scrubbed
        assert scrubbed.count(WITHHELD) == 4 and "/speakers/me/" in scrubbed
        assert scrubbed.startswith(
            "Go " + WITHHELD + " and Accept " + WITHHELD + " or " + WITHHELD + " or "
        )
        assert '"titled"' not in scrubbed

    def test_failed_send_keeps_the_error_and_not_the_body(self):
        with patch(
            "common.send_emails.deliver_markdown_email",
            side_effect=RuntimeError("smtp down"),
        ):
            with pytest.raises(RuntimeError):
                send(["someone@example.com"])
        record = SentEmail.objects.get()
        assert record.status == SentEmailStatus.FAILED and record.failed
        assert record.error == "RuntimeError: smtp down"
        assert record.body_md == ""

    def test_account_emails_leave_no_record(self, client, ada):
        """Password resets go through the allauth adapter, never the record:
        a live reset link is not something a trail should hold."""
        EmailAddress.objects.create(
            user=ada, email=ada.email, primary=True, verified=True
        )
        client.post(reverse("account_reset_password"), {"email": ada.email})
        assert len(mail.outbox) == 1
        assert not SentEmail.objects.exists()


@pytest.mark.django_db
class TestOwnership:
    def test_owned_by_account_or_presenter_never_by_address(self, ada, presenter):
        mine_by_account = send([ada.email], {"user": ada})
        # The invitation went out before Ada had an account: no user on the
        # record, and the presenter row is hers now.
        mine_by_presenter = send([presenter.email], {"presenter": presenter})
        SentEmail.objects.filter(pk=mine_by_presenter.pk).update(user=None)
        other = User.objects.create_user(username="grace", email="g@example.com")
        send([other.email], {"user": other})
        # Sent to her address, but nothing proves the address is hers.
        send([ada.email], {})
        assert set(SentEmail.objects.owned_by(ada)) == {
            mine_by_account,
            mine_by_presenter,
        }


@pytest.mark.django_db
class TestRetention:
    def test_past_retention(self, conference, settings):
        settings.EMAIL_RECORD_RETENTION_DAYS = 365
        today = date(2026, 9, 26)
        old = Conference.objects.create(
            year=2022, name="2022", slug="2022", end_date=date(2022, 12, 4)
        )
        undated = Conference.objects.create(year=2020, name="2020", slug="2020")
        conference.end_date = today - timedelta(days=1)
        conference.save()
        expired = [
            send(["a@x.org"], conference=old),
            send(["a@x.org"], conference=undated),
        ]
        kept = [send(["a@x.org"], conference=conference), send(["a@x.org"])]
        stale = send(["a@x.org"])
        SentEmail.objects.filter(pk=stale.pk).update(
            sent_at=timezone.now() - timedelta(days=400)
        )
        assert set(SentEmail.objects.past_retention(today)) == {*expired, stale}
        assert not set(SentEmail.objects.past_retention(today)) & set(kept)

    def test_prune_counts_and_dry_run_keeps_rows(self):
        old = Conference.objects.create(
            year=2020, name="2020", slug="2020", end_date=date(2020, 12, 1)
        )
        send(["a@x.org"], conference=old)
        send(["a@x.org"])
        assert prune_sent_emails(dry_run=True) == 1
        assert SentEmail.objects.count() == 2
        assert prune_sent_emails() == 1
        assert SentEmail.objects.count() == 1

    def test_command_reports(self):
        old = Conference.objects.create(
            year=2020, name="2020", slug="2020", end_date=date(2020, 12, 1)
        )
        send(["a@x.org"], conference=old)
        out = StringIO()
        call_command("prune_email_records", "--dry-run", stdout=out)
        assert "Would delete 1 email record(s)" in out.getvalue()
        assert SentEmail.objects.count() == 1
        out = StringIO()
        call_command("prune_email_records", stdout=out)
        assert "Deleted 1 email record(s)" in out.getvalue()
        assert not SentEmail.objects.exists()

    def test_task_returns_a_summary(self):
        assert prune_email_records_task() == "Deleted 0 email record(s) past retention"

    def test_periodic_task_is_seeded_once_and_removable(self):
        migration.seed_periodic_tasks(apps, None)
        migration.seed_periodic_tasks(apps, None)
        task = PeriodicTask.objects.get(name=migration.TASK_NAME)
        assert task.task == prune_email_records_task.name
        assert (task.crontab.hour, task.crontab.minute) == ("3", "30")
        migration.unseed_periodic_tasks(apps, None)
        assert not PeriodicTask.objects.filter(name=migration.TASK_NAME).exists()


def test_kind_of():
    assert kind_of("emails/speakers/invitation.md") == "speakers/invitation"
    assert kind_of("other.md") == "other"


@pytest.mark.django_db
class TestAdmin:
    def test_read_only(self, client, admin_user):
        record = send(["a@x.org"])
        client.force_login(admin_user)
        assert (
            client.get(reverse("admin:common_sentemail_changelist")).status_code == 200
        )
        assert client.get(reverse("admin:common_sentemail_add")).status_code == 403
        # The change page opens as the read-only view Django gives a
        # superuser with no change permission: nothing to save.
        change = reverse("admin:common_sentemail_change", args=[record.pk])
        assert 'name="_save"' not in client.get(change).content.decode()
        delete = reverse("admin:common_sentemail_delete", args=[record.pk])
        assert client.get(delete).status_code == 403
