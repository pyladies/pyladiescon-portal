import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile
from speakers.models import ActivityLog
from speakers.services import accept_invitation, send_invitation
from speakers.tasks import send_acceptance_email_task

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

WELCOME = reverse("speakers:my_welcome")
DASHBOARD = reverse("speakers:my_dashboard")
DISMISS = reverse("speakers:my_dismiss_password_reminder")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def newcomer(conference, enabled):
    """A presenter who just accepted: account without password or profile."""
    session = make_session(conference, title="Django 101")
    presenter = make_presenter(
        conference, display_name="Ada Lovelace", email="ada@example.com"
    )
    add_presenter(session, presenter)
    invitation = make_invitation(presenter, session)
    send_invitation(invitation)
    accept_invitation(invitation)
    presenter.refresh_from_db()
    return presenter


def valid_data(**overrides):
    data = {
        "username": "ada",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "pronouns": "she/her",
        "coc_agreement": "on",
        "tos_agreement": "on",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
@pytest.mark.no_agreements
class TestWelcomeFlow:
    """The welcome page is where a presenter agrees, so these run against
    the real ``has_agreed`` rather than the suite-wide stand-in."""

    def test_dashboard_redirects_to_welcome_until_onboarded(self, client, newcomer):
        client.force_login(newcomer.user)
        assertRedirects(client.get(DASHBOARD), WELCOME)
        assertRedirects(client.get(reverse("speakers:my_profile")), WELCOME)
        assertRedirects(
            client.get(reverse("index")), WELCOME, fetch_redirect_response=False
        )

    def test_welcome_prefills_and_lists_agreements(self, client, newcomer):
        client.force_login(newcomer.user)
        response = client.get(WELCOME)
        form = response.context["form"]
        assert form.initial["username"] == "ada"
        assert (
            form.initial["first_name"] == "Ada"
            and form.initial["last_name"] == "Lovelace"
        )
        content = response.content.decode()
        assert "Code of Conduct" in content and "Terms of Service" in content
        assert "Password" in content and "(optional)" in content

    def test_complete_without_password(self, client, newcomer):
        client.force_login(newcomer.user)
        response = client.post(WELCOME, valid_data(username="ada.l"), follow=True)
        assert response.redirect_chain[-1][0] == DASHBOARD
        content = response.content.decode()
        assert "sign in with an emailed code any time" in content
        assert 'id="password-reminder"' in content
        user = User.objects.get(pk=newcomer.user.pk)
        assert user.username == "ada.l" and user.has_usable_password() is False
        profile = PortalProfile.objects.get(user=user)
        assert profile.coc_agreement and profile.tos_agreement
        assert profile.pronouns == "she/her"
        assert ActivityLog.objects.get(action="presenter.onboarded").data == {
            "password_set": False
        }

    def test_complete_with_password_keeps_session_and_hides_reminder(
        self, client, newcomer
    ):
        client.force_login(newcomer.user)
        response = client.post(
            WELCOME,
            valid_data(
                password1="correct-horse-battery", password2="correct-horse-battery"
            ),
            follow=True,
        )
        assert response.redirect_chain[-1][0] == DASHBOARD
        assert int(client.session["_auth_user_id"]) == newcomer.user.pk
        user = User.objects.get(pk=newcomer.user.pk)
        assert user.check_password("correct-horse-battery")
        assert 'id="password-reminder"' not in response.content.decode()
        client.logout()
        assert client.login(username="ada", password="correct-horse-battery")

    def test_validation(self, client, newcomer, portal_user):
        client.force_login(newcomer.user)
        response = client.post(WELCOME, valid_data(coc_agreement="", tos_agreement=""))
        errors = response.context["form"].errors
        assert "coc_agreement" in errors and "tos_agreement" in errors
        response = client.post(WELCOME, valid_data(username="TESTUSER"))
        assert response.context["form"].errors["username"] == [
            "That username is taken."
        ]
        response = client.post(WELCOME, valid_data(password1="abc", password2="abd"))
        assert "do not match" in response.context["form"].errors["password2"][0]
        response = client.post(WELCOME, valid_data(password1="abc", password2="abc"))
        assert "password1" in response.context["form"].errors
        assert not PortalProfile.objects.filter(user=newcomer.user).exists()

    def test_already_onboarded_skips_welcome(self, client, newcomer):
        """Onboarded means they agreed, not merely that a row exists: a
        profile without the agreements sends them back here."""
        PortalProfile.objects.create(
            user=newcomer.user, coc_agreement=True, tos_agreement=True
        )
        client.force_login(newcomer.user)
        assertRedirects(client.get(WELCOME), DASHBOARD)
        assert client.get(DASHBOARD).status_code == 200

    def test_non_presenter_forbidden(self, client, portal_user, enabled):
        """Past the gate (they have agreed), the page is still not theirs."""
        PortalProfile.objects.create(
            user=portal_user, coc_agreement=True, tos_agreement=True
        )
        client.force_login(portal_user)
        assert client.get(WELCOME).status_code == 403


@pytest.mark.django_db
class TestPasswordReminder:
    def test_dismiss(self, client, newcomer):
        client.force_login(newcomer.user)
        client.post(WELCOME, valid_data())  # onboard without a password first
        assert 'id="password-reminder"' in client.get(DASHBOARD).content.decode()
        response = client.post(DISMISS, follow=True)
        assert "sign-in codes it is" in response.content.decode()
        newcomer.refresh_from_db()
        assert newcomer.password_reminder_dismissed is True
        assert 'id="password-reminder"' not in client.get(DASHBOARD).content.decode()

    def test_no_reminder_with_a_password(self, client, conference, enabled):
        user = User.objects.create_user(username="grace", password="pw-with-9-chars")
        make_presenter(conference, user=user)
        client.force_login(user)
        assert 'id="password-reminder"' not in client.get(DASHBOARD).content.decode()


@pytest.mark.django_db
class TestAcceptanceEmail:
    def test_sent_on_accept(self, conference, enabled):
        session = make_session(conference, title="Django 101", kind="WORKSHOP")
        presenter = make_presenter(
            conference, display_name="Ada Lovelace", email="ada@example.com"
        )
        add_presenter(session, presenter, role="PRESENTER")
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        mail.outbox.clear()
        accept_invitation(invitation)
        welcome = [m for m in mail.outbox if "Welcome aboard" in m.subject]
        assert len(welcome) == 1
        body = welcome[0].body
        assert welcome[0].to == ["ada@example.com"]
        assert "Username: ada" in body and "Email: ada@example.com" in body
        assert "Send me a sign-in code" in body
        assert "/accounts/password/set/" in body
        assert "Django 101" in body and "Workshop, presenter" in body
        assert "/speakers/me/" in body
        assert "what the team is doing for you" in body

    def test_task_ignores_unaccepted(self, conference, enabled):
        invitation = make_invitation(make_presenter(conference))
        assert "not accepted" in send_acceptance_email_task(invitation.pk)
        assert "not accepted" in send_acceptance_email_task(999999)
