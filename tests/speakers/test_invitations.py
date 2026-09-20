import re
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.urls import reverse

from portal.models import Conference
from speakers.constants import SessionStatus
from speakers.emails import signed_invitation_token
from speakers.models import ActivityLog, Invitation, InvitationStatus
from speakers.services import (
    InvitationError,
    accept_invitation,
    cancel_invitation,
    resolve_invitation,
    send_invitation,
)
from speakers.signals import invitation_accepted
from speakers.tasks import send_invitation_email_task

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def invitation(conference, enabled):
    session = make_session(conference, kind="WORKSHOP", title="Django 101")
    presenter = make_presenter(
        conference, display_name="Ada Lovelace", email="ada@example.com"
    )
    add_presenter(session, presenter)
    return make_invitation(presenter, session, message_md="Hope you can **join**!")


def _url(invitation):
    return reverse("speakers:invitation", args=[signed_invitation_token(invitation)])


def _link_from_mail():
    """The invitation path as it appears in the last email sent.

    Signed tokens carry a timestamp, so re-signing in the test a second later
    would not match the email byte for byte.
    """
    return re.search(r"/speakers/invitations/[^\s)>]+/", mail.outbox[-1].body).group(0)


@pytest.mark.django_db
class TestSendInvitation:
    def test_send_issues_token_and_email(self, invitation, admin_user, send):
        mail.outbox.clear()
        send(invitation, actor=admin_user)
        invitation.refresh_from_db()
        assert invitation.token
        assert invitation.sent_at is not None
        assert invitation.expires_at == invitation.sent_at + timedelta(days=14)
        assert invitation.status == InvitationStatus.SENT
        assert invitation.session.status == SessionStatus.INVITED
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == ["ada@example.com"]
        assert "Django 101" in message.subject
        assert "Hope you can join!" in message.body
        assert "Django 101 (Workshop)" in message.body
        html = message.alternatives[0][0]
        assert "<strong>join</strong>" in html
        link = _link_from_mail()
        assert link in html
        assert (
            resolve_invitation(link.split("/")[3], invitation.conference) == invitation
        )
        entry = ActivityLog.for_target(invitation).get()
        assert entry.action == "invitation.sent"
        assert entry.actor == admin_user

    def test_url_in_text_part_is_usable(self, send, invitation):
        """The plain-text part loses link targets, so the address is also
        written out as an autolink that survives the text conversion."""
        send(invitation)
        link = _link_from_mail()
        assert link in mail.outbox[-1].alternatives[0][0]
        assert (
            resolve_invitation(link.split("/")[3], invitation.conference) == invitation
        )

    def test_resend_invalidates_previous_token(self, invitation):
        send_invitation(invitation)
        old_url = _url(invitation)
        send_invitation(invitation)
        invitation.refresh_from_db()
        assert invitation.session.status == SessionStatus.INVITED
        with pytest.raises(InvitationError, match="superseded"):
            resolve_invitation(old_url.rsplit("/", 2)[1], invitation.conference)
        assert (
            resolve_invitation(
                signed_invitation_token(invitation), invitation.conference
            )
            == invitation
        )

    def test_resend_after_decline_reopens(self, invitation):
        send_invitation(invitation)
        invitation.declined_at = invitation.sent_at
        invitation.save()
        assert invitation.status == InvitationStatus.DECLINED
        send_invitation(invitation)
        assert invitation.status == InvitationStatus.SENT

    def test_cannot_resend_accepted(self, invitation):
        send_invitation(invitation)
        accept_invitation(invitation)
        with pytest.raises(ValueError, match="already been accepted"):
            send_invitation(invitation)

    def test_general_invitation_without_session(self, conference, enabled, send):
        presenter = make_presenter(conference)
        invitation = make_invitation(presenter)
        mail.outbox.clear()
        send(invitation)
        assert str(invitation) == f"Invitation for {presenter} to {conference}"
        assert mail.outbox[0].subject.endswith("You're invited to PyLadiesCon 2025")

    def test_task_with_missing_invitation(self):
        assert "not found" in send_invitation_email_task(999999)

    def test_rejects_mixed_editions(self, conference):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        session = make_session(other)
        presenter = make_presenter(conference)
        with pytest.raises(ValidationError, match="different editions"):
            make_invitation(presenter, session)


@pytest.mark.django_db
class TestResolveInvitation:
    def test_bad_signature(self, invitation):
        with pytest.raises(InvitationError, match="invalid"):
            resolve_invitation("not-a-token", invitation.conference)

    def test_unknown_invitation(self, invitation):
        send_invitation(invitation)
        token = signed_invitation_token(invitation)
        invitation.delete()
        with pytest.raises(InvitationError, match="invalid"):
            resolve_invitation(token, invitation.conference)

    def test_signature_expiry(self, invitation, monkeypatch):
        send_invitation(invitation)
        monkeypatch.setattr(Invitation, "TOKEN_MAX_AGE", timedelta(seconds=-1))
        with pytest.raises(InvitationError, match="expired"):
            resolve_invitation(
                signed_invitation_token(invitation), invitation.conference
            )

    def test_expires_at_passed(self, invitation):
        send_invitation(invitation)
        invitation.expires_at = invitation.sent_at - timedelta(seconds=1)
        invitation.save()
        assert invitation.status == InvitationStatus.EXPIRED
        with pytest.raises(InvitationError, match="expired"):
            resolve_invitation(
                signed_invitation_token(invitation), invitation.conference
            )

    def test_wrong_edition(self, invitation):
        send_invitation(invitation)
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        with pytest.raises(InvitationError, match="invalid"):
            resolve_invitation(signed_invitation_token(invitation), other)

    def test_reuse_after_accept(self, invitation):
        send_invitation(invitation)
        accept_invitation(invitation)
        with pytest.raises(InvitationError, match="accepted"):
            resolve_invitation(
                signed_invitation_token(invitation), invitation.conference
            )

    def test_cancelled(self, invitation, admin_user):
        send_invitation(invitation)
        cancel_invitation(invitation, actor=admin_user)
        assert invitation.status == InvitationStatus.CANCELLED
        with pytest.raises(InvitationError, match="cancelled"):
            resolve_invitation(
                signed_invitation_token(invitation), invitation.conference
            )

    def test_unsent_is_draft(self, invitation):
        assert invitation.status == InvitationStatus.DRAFT
        assert invitation.is_open is False


@pytest.mark.django_db
class TestAcceptInvitation:
    def test_creates_user_and_confirms(self, invitation):
        send_invitation(invitation)
        received = []
        invitation_accepted.connect(lambda **kw: received.append(kw), weak=False)
        user = accept_invitation(invitation)
        assert user.username == "ada"
        assert user.email == "ada@example.com"
        assert user.first_name == "Ada" and user.last_name == "Lovelace"
        assert user.has_usable_password() is False
        address = EmailAddress.objects.get(user=user)
        assert address.email == "ada@example.com"
        assert address.verified is True and address.primary is True
        invitation.presenter.refresh_from_db()
        assert invitation.presenter.user == user
        link = invitation.session.session_presenters.get()
        assert link.is_confirmed is True
        invitation.session.refresh_from_db()
        assert invitation.session.status == SessionStatus.CONFIRMED
        assert invitation.status == InvitationStatus.ACCEPTED
        assert received[0]["invitation"] == invitation
        assert received[0]["presenter"] == invitation.presenter
        assert received[0]["user"] == user
        actions = [
            e.action
            for e in ActivityLog.objects.filter(conference=invitation.conference)
        ]
        assert "invitation.accepted" in actions
        assert "session.confirmed" in actions

    def test_matching_user_email_alone_does_not_link(self, invitation, portal_user):
        """``User.email`` proves nothing; only a verified address does."""
        portal_user.email = "ADA@example.com"
        portal_user.save()
        send_invitation(invitation)
        user = accept_invitation(invitation)
        assert user != portal_user and user.username == "ada"
        assert not EmailAddress.objects.filter(user=portal_user).exists()

    def test_unverified_signup_cannot_take_over_the_presenter(
        self, invitation, django_user_model
    ):
        """Mallory signed up with Ada's address and never verified it. Ada's
        invitation must not link to that account, which would hand Mallory
        a verified address and Ada's speaker profile behind Mallory's
        password. The unverified claim is dropped, as allauth does on
        confirmation, and Ada gets her own account."""
        mallory = django_user_model.objects.create_user(
            username="mallory", email="ada@example.com", password="secret-pw"
        )
        EmailAddress.objects.create(
            user=mallory, email="ada@example.com", verified=False, primary=True
        )
        send_invitation(invitation)
        user = accept_invitation(invitation)
        assert user != mallory
        assert user.has_usable_password() is False
        assert not EmailAddress.objects.filter(user=mallory).exists()
        address = EmailAddress.objects.get(email="ada@example.com")
        assert address.user == user and address.verified is True
        invitation.presenter.refresh_from_db()
        assert invitation.presenter.user == user
        mallory.refresh_from_db()
        assert mallory.check_password("secret-pw")  # untouched, just unlinked

    def test_deactivated_account_is_not_linked(self, client, invitation, portal_user):
        """A verified address on a deactivated account must not capture the
        presenter: the login would not stick and they would be told they are
        signed in while logged out. The dormant row is dropped (allauth
        allows one verified row per address) and a fresh account is made."""
        EmailAddress.objects.create(
            user=portal_user, email="ada@example.com", verified=True, primary=True
        )
        portal_user.is_active = False
        portal_user.save()
        send_invitation(invitation)
        response = client.post(_url(invitation), {"action": "accept"})
        assert response.status_code == 302
        user = User.objects.get(username="ada")
        assert user != portal_user and user.is_active
        assert int(client.session["_auth_user_id"]) == user.pk
        address = EmailAddress.objects.get(email="ada@example.com")
        assert address.user == user and address.verified
        portal_user.refresh_from_db()
        assert portal_user.is_active is False
        assert not EmailAddress.objects.filter(user=portal_user).exists()

    def test_already_linked_presenter_keeps_user(self, invitation, portal_user):
        invitation.presenter.user = portal_user
        invitation.presenter.save()
        send_invitation(invitation)
        assert accept_invitation(invitation) == portal_user

    def test_failing_receiver_rolls_everything_back(self, invitation):
        """A Stage 2 receiver that blows up must not leave the account linked
        and the session half confirmed."""
        send_invitation(invitation)

        def explode(**kwargs):
            raise RuntimeError("checklist instantiation failed")

        invitation_accepted.connect(explode, weak=False)
        try:
            with pytest.raises(RuntimeError):
                accept_invitation(invitation)
        finally:
            invitation_accepted.disconnect(explode)
        invitation.refresh_from_db()
        invitation.presenter.refresh_from_db()
        assert invitation.accepted_at is None
        assert invitation.presenter.user is None
        assert not User.objects.filter(username="ada").exists()
        assert invitation.session.session_presenters.get().is_confirmed is False

    def test_email_is_queued_only_after_commit(
        self, invitation, django_capture_on_commit_callbacks
    ):
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            send_invitation(invitation)
            assert mail.outbox == []  # nothing goes out inside the transaction
        assert len(callbacks) == 1
        callbacks[0]()
        assert len(mail.outbox) == 1

    def test_accepting_verifies_the_address_the_link_went_to(self, invitation):
        """Changing the presenter's email after sending must not let whoever
        holds the old address claim the new one as verified."""
        send_invitation(invitation)
        assert invitation.sent_to == "ada@example.com"
        invitation.presenter.email = "ada@new.example"
        invitation.presenter.save()
        user = accept_invitation(invitation)
        assert user.email == "ada@example.com"
        assert not EmailAddress.objects.filter(email="ada@new.example").exists()
        # A resend snapshots the current address again.
        later = make_invitation(make_presenter(invitation.conference, email="b@x.io"))
        send_invitation(later)
        assert later.sent_to == "b@x.io"

    def test_username_collision_gets_suffix(self, invitation):
        User.objects.create_user(username="ada", email="other@example.com")
        send_invitation(invitation)
        assert accept_invitation(invitation).username == "ada2"

    def test_username_from_dotted_local_part(self, conference, enabled):
        presenter = make_presenter(conference, email="ada.lovelace@example.com")
        invitation = make_invitation(presenter)
        send_invitation(invitation)
        assert accept_invitation(invitation).username == "ada.lovelace"

    def test_session_waits_for_all_required_presenters(self, conference, enabled):
        panel = make_session(conference, kind="PANEL")
        moderator = make_presenter(conference)
        panelist = make_presenter(conference)
        guest = make_presenter(conference)
        add_presenter(panel, moderator, role="MODERATOR")
        add_presenter(panel, panelist, role="PANELIST")
        add_presenter(panel, guest, role="PANELIST", is_required=False)
        first = make_invitation(moderator, panel)
        second = make_invitation(panelist, panel)
        send_invitation(first)
        send_invitation(second)
        accept_invitation(first)
        panel.refresh_from_db()
        assert panel.status == SessionStatus.INVITED
        accept_invitation(second)
        panel.refresh_from_db()
        assert panel.status == SessionStatus.CONFIRMED

    def test_general_invitation_confirms_every_session(self, conference, enabled):
        presenter = make_presenter(conference)
        talk = make_session(conference, kind="TALK")
        panel = make_session(conference, kind="PANEL")
        add_presenter(talk, presenter)
        add_presenter(panel, presenter, role="PANELIST")
        invitation = make_invitation(presenter)
        send_invitation(invitation)
        accept_invitation(invitation)
        assert talk.session_presenters.get().is_confirmed
        assert panel.session_presenters.get().is_confirmed
        talk.refresh_from_db()
        panel.refresh_from_db()
        assert talk.status == SessionStatus.CONFIRMED
        assert panel.status == SessionStatus.CONFIRMED

    def test_already_confirmed_session_untouched(self, conference, enabled):
        session = make_session(conference, kind="OPENING")
        session.confirm()
        presenter = make_presenter(conference)
        add_presenter(session, presenter, role="HOST")
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        accept_invitation(invitation)
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED
        assert not ActivityLog.objects.filter(action="session.confirmed").exists()


@pytest.mark.django_db
class TestInvitationView:
    def test_404_when_module_disabled(self, client, conference):
        presenter = make_presenter(conference)
        invitation = make_invitation(presenter)
        send_invitation(invitation)
        assert client.get(_url(invitation)).status_code == 404

    def test_404_for_other_editions_invitation(self, client, enabled):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        invitation = make_invitation(make_presenter(other))
        send_invitation(invitation)
        response = client.get(_url(invitation))
        assert response.status_code == 200
        assert response.context["reason"] == "invalid"

    def test_get_marks_opened_and_shows_message(self, client, invitation):
        send_invitation(invitation)
        response = client.get(_url(invitation))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Django 101" in content
        assert "<strong>join</strong>" in content
        invitation.refresh_from_db()
        assert invitation.opened_at is not None
        assert invitation.status == InvitationStatus.OPENED
        opened = invitation.opened_at
        client.get(_url(invitation))
        invitation.refresh_from_db()
        assert invitation.opened_at == opened

    def test_invalid_link_page(self, client, enabled):
        response = client.get(reverse("speakers:invitation", args=["nope"]))
        assert response.status_code == 200
        assert response.context["reason"] == "invalid"
        assert "not valid" in response.content.decode()

    def test_accept_logs_in_and_redirects(self, client, invitation):
        send_invitation(invitation)
        response = client.post(_url(invitation), {"action": "accept"})
        assert response.status_code == 302
        assert response.url == reverse("speakers:index")
        user = User.objects.get(username="ada")
        assert int(client.session["_auth_user_id"]) == user.pk
        follow = client.get(response.url, follow=True)
        assert follow.redirect_chain[-1][0] == reverse("speakers:my_dashboard")
        assert "Thanks for accepting, Ada Lovelace" in follow.content.decode()

    def test_accept_switches_logged_in_user(self, client, invitation, portal_user):
        client.force_login(portal_user)
        send_invitation(invitation)
        client.post(_url(invitation), {"action": "accept"})
        assert (
            int(client.session["_auth_user_id"]) == User.objects.get(username="ada").pk
        )

    def test_accept_keeps_matching_logged_in_user(
        self, client, invitation, portal_user
    ):
        EmailAddress.objects.create(
            user=portal_user, email="ada@example.com", verified=True, primary=True
        )
        client.force_login(portal_user)
        send_invitation(invitation)
        client.post(_url(invitation), {"action": "accept"})
        assert int(client.session["_auth_user_id"]) == portal_user.pk

    def test_post_used_link_shows_reason(self, client, invitation):
        send_invitation(invitation)
        client.post(_url(invitation), {"action": "accept"})
        client.logout()
        response = client.post(_url(invitation), {"action": "accept"})
        assert response.context["reason"] == "accepted"

    def test_decline(self, client, invitation):
        send_invitation(invitation)
        response = client.post(_url(invitation), {"action": "decline"})
        assert response.status_code == 200
        assert "Thanks for letting us know" in response.content.decode()
        invitation.refresh_from_db()
        assert invitation.status == InvitationStatus.DECLINED
        assert invitation.session.session_presenters.get().is_confirmed is False
        assert (
            ActivityLog.for_target(invitation).first().action == "invitation.declined"
        )
        response = client.get(_url(invitation))
        assert response.context["reason"] == "declined"

    @pytest.mark.parametrize(
        "reason", ["expired", "superseded", "accepted", "declined", "cancelled"]
    )
    def test_invalid_page_wording(self, client, enabled, reason):
        html = render_to_string("speakers/invitation_invalid.html", {"reason": reason})
        assert f'data-reason="{reason}"' in html


@pytest.mark.django_db
class TestLoginByCode:
    def test_login_page_offers_code_sign_in(self, client):
        content = client.get(reverse("account_login")).content.decode()
        assert reverse("account_request_login_code") in content

    def test_presenter_can_request_code(self, client, invitation):
        send_invitation(invitation)
        accept_invitation(invitation)
        mail.outbox.clear()
        response = client.post(
            reverse("account_request_login_code"), {"email": "ada@example.com"}
        )
        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["ada@example.com"]


@pytest.mark.django_db
class TestInvitationAdmin:
    def test_changelist(self, client, admin_user, invitation):
        send_invitation(invitation)
        client.force_login(admin_user)
        response = client.get(reverse("admin:speakers_invitation_changelist"))
        assert response.status_code == 200
        assert "Ada Lovelace" in response.content.decode()
