"""The Code of Conduct and Terms of Service gate.

Signup collects both agreements, but an account can arrive without ever
meeting that form: a speaker invitation creates one and signs the person in,
and a sign-in code lets them back in afterwards. These tests use the
``no_agreements`` marker, so the real predicate runs rather than the
suite-wide stand-in in ``conftest.py``.
"""

import re

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.agreements import (
    AGREED_KEY,
    MAX_TRIES,
    AgreementRequiredMiddleware,
    agreement_url_for,
    has_agreed,
)
from portal_account.models import PortalProfile
from speakers.models import Presenter
from speakers.services import send_invitation
from tests.speakers.factories import (
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

AGREEMENTS = reverse("portal_account:agreements")

pytestmark = [pytest.mark.django_db, pytest.mark.no_agreements]


@pytest.fixture
def user(db):
    return User.objects.create_user(username="newcomer", email="new@example.com")


class TestPredicate:
    def test_needs_both(self, user):
        assert has_agreed(user) is False
        profile = PortalProfile.objects.create(user=user, coc_agreement=True)
        assert has_agreed(user) is False
        profile.tos_agreement = True
        profile.save()
        assert has_agreed(user) is True


class TestGate:
    def test_a_new_account_is_sent_to_the_page(self, client, user):
        """No profile at all: the state a speaker invitation leaves behind."""
        client.force_login(user)
        assertRedirects(client.get(reverse("index")), AGREEMENTS)
        assertRedirects(client.get(reverse("volunteer:index")), AGREEMENTS)

    def test_a_profile_without_the_agreements_is_sent_too(self, client, user):
        """The profile form cannot record them, so this state is reachable."""
        PortalProfile.objects.create(user=user)
        client.force_login(user)
        assertRedirects(client.get(reverse("index")), AGREEMENTS)

    def test_a_post_is_redirected_as_well(self, client, user):
        client.force_login(user)
        response = client.post(reverse("volunteer:index"), {})
        assert response.status_code == 302 and response["Location"] == AGREEMENTS

    def test_agreeing_records_both_and_returns(self, client, user):
        client.force_login(user)
        page = client.get(AGREEMENTS)
        assert page.status_code == 200
        assert "Code of Conduct" in page.content.decode()
        response = client.post(
            AGREEMENTS,
            {"coc_agreement": "on", "tos_agreement": "on", "next": reverse("index")},
        )
        assert response.status_code == 302
        profile = PortalProfile.objects.get(user=user)
        assert profile.coc_agreement is True and profile.tos_agreement is True
        # The gate is quiet from here on.
        assert client.get(reverse("volunteer:index")).status_code == 200

    def test_an_account_with_no_name_is_asked_for_one(self, client, user):
        """Creating the profile here means the portal index stops asking, so
        the gate hands them straight to the form that does."""
        client.force_login(user)
        response = client.post(
            AGREEMENTS, {"coc_agreement": "on", "tos_agreement": "on"}
        )
        profile = PortalProfile.objects.get(user=user)
        assert response.status_code == 302
        assert response["Location"] == reverse(
            "portal_account:portal_profile_edit", args=[profile.pk]
        )

    def test_an_account_with_a_name_carries_on(self, client, user):
        user.first_name = "Ada"
        user.save()
        client.force_login(user)
        response = client.post(
            AGREEMENTS,
            {"coc_agreement": "on", "tos_agreement": "on", "next": reverse("index")},
        )
        assert response["Location"] == reverse("index")

    def test_one_box_is_not_enough(self, client, user):
        client.force_login(user)
        response = client.post(AGREEMENTS, {"coc_agreement": "on"})
        assert response.status_code == 200
        assert has_agreed(user) is False

    def test_signing_out_still_works(self, client, user):
        """An exempt path: a gated account can still leave."""
        client.force_login(user)
        assert client.get("/accounts/logout/").status_code in (200, 302)

    @pytest.mark.parametrize(
        "path, exempt",
        [
            ("/accounts/login/", True),
            ("/admin/", True),
            ("/captcha/image/abc/", True),
            ("/static/portal.css", True),
            ("/media/profile_pictures/ada.png", True),
            ("/volunteer/", False),
            ("/speakers/me/", False),
        ],
    )
    def test_which_paths_the_gate_leaves_alone(self, rf, path, exempt):
        """Whitenoise serves the real static files before the gate is
        reached, so the asset prefixes are checked here directly."""
        middleware = AgreementRequiredMiddleware(lambda request: None)
        assert middleware._exempt(rf.get(path)) is exempt

    def test_anonymous_visitors_pass(self, client):
        assert client.get(reverse("index")).status_code == 200

    def test_an_agreed_account_is_untouched(self, client, user):
        PortalProfile.objects.create(user=user, coc_agreement=True, tos_agreement=True)
        client.force_login(user)
        assert client.get(reverse("volunteer:index")).status_code == 200


class TestResolver:
    def test_a_presenter_goes_to_the_speaker_welcome_page(self, user, conference):
        make_settings(conference)
        Presenter.objects.create(
            conference=conference, user=user, display_name="Ada", email="a@example.com"
        )
        assert agreement_url_for(user) == reverse("speakers:my_welcome")

    def test_everyone_else_goes_to_the_plain_page(self, user, conference):
        make_settings(conference)
        assert agreement_url_for(user) == AGREEMENTS

    def test_no_speaker_module_no_speaker_page(self, user, conference):
        """The resolver answers even with the module off for this edition."""
        assert agreement_url_for(user) == AGREEMENTS

    def test_the_gate_sends_a_presenter_to_the_welcome_page(
        self, client, user, conference
    ):
        make_settings(conference)
        Presenter.objects.create(
            conference=conference, user=user, display_name="Ada", email="a@example.com"
        )
        client.force_login(user)
        assertRedirects(
            client.get(reverse("index")),
            reverse("speakers:my_welcome"),
            target_status_code=200,
        )


class TestAnonymousHelper:
    def test_predicate_on_an_anonymous_user(self):
        assert has_agreed(AnonymousUser()) is False


class TestTheFlowsItSitsInFrontOf:
    """The gate with the real predicate, in the paths it now guards.

    The rest of the suite treats every account as agreed (``conftest.py``),
    which is what let an infinite redirect through with full coverage. These
    carry the marker, so they see what a real visitor sees.
    """

    @pytest.fixture
    def presenter_user(self, conference):
        make_settings(conference)
        user = User.objects.create_user(username="ada", email="ada@example.com")
        Presenter.objects.create(
            conference=conference,
            user=user,
            display_name="Ada",
            email="ada@example.com",
        )
        return user

    def test_a_profile_that_predates_the_agreements_does_not_loop(
        self, client, presenter_user
    ):
        """The state every existing account is in: a profile, no agreement.

        The gate sends them to the welcome page; the welcome page used to
        send them back because it asked whether a profile existed.
        """
        PortalProfile.objects.create(user=presenter_user)
        client.force_login(presenter_user)
        welcome = reverse("speakers:my_welcome")
        assertRedirects(
            client.get(reverse("speakers:my_dashboard")),
            welcome,
            target_status_code=200,
        )
        page = client.get(welcome)
        assert page.status_code == 200 and "Code of Conduct" in page.content.decode()
        response = client.post(
            welcome,
            {
                "username": "ada",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "coc_agreement": "on",
                "tos_agreement": "on",
            },
        )
        assert response.status_code == 302
        assert has_agreed(presenter_user) is True
        assert client.get(reverse("speakers:my_dashboard")).status_code == 200

    def test_a_presenter_with_no_profile_reaches_the_welcome_page(
        self, client, presenter_user
    ):
        client.force_login(presenter_user)
        assertRedirects(
            client.get(reverse("speakers:my_dashboard")),
            reverse("speakers:my_welcome"),
            target_status_code=200,
        )

    def test_accepting_an_invitation_still_works(
        self, client, conference, django_capture_on_commit_callbacks
    ):
        """Acceptance creates the account and signs them in; the gate must
        not break the redirect that lands them in the portal."""
        make_settings(conference)
        presenter = make_presenter(conference, display_name="Grace")
        invitation = make_invitation(presenter, make_session(conference))
        # The email is queued on commit, which a test transaction never does.
        with django_capture_on_commit_callbacks(execute=True):
            send_invitation(invitation)
        token = re.search(
            r"/speakers/invitations/([^\s)/]+)/", mail.outbox[-1].body
        ).group(1)
        response = client.post(
            reverse("speakers:invitation", args=[token]), {"action": "accept"}
        )
        assert response.status_code == 302
        presenter.refresh_from_db()
        assert presenter.user is not None
        # Wherever it points, following it must settle rather than bounce.
        landing = client.get(response["Location"], follow=True)
        assert landing.status_code == 200
        assert landing.redirect_chain[-1][0].endswith("/welcome/")

    def test_staff_reach_the_admin(self, client):
        staff = User.objects.create_user(
            username="boss", email="boss@example.com", is_staff=True, is_superuser=True
        )
        client.force_login(staff)
        assert client.get("/admin/").status_code == 200

    def test_a_page_that_cannot_collect_the_agreement_is_dropped(
        self, client, presenter_user, monkeypatch
    ):
        """The loop guard: a resolver pointing somewhere that does not ask
        is used once, then the gate falls back to its own page."""
        dead_end = reverse("speakers:my_sessions")
        monkeypatch.setattr(
            "portal_account.agreements.agreement_url_for", lambda user: dead_end
        )
        client.force_login(presenter_user)
        hub = reverse("volunteer:index")
        for _ in range(MAX_TRIES):
            assert client.get(hub)["Location"] == dead_end
        assert client.get(hub)["Location"] == AGREEMENTS

    def test_the_settled_answer_is_remembered(self, client, presenter_user):
        PortalProfile.objects.create(
            user=presenter_user, coc_agreement=True, tos_agreement=True
        )
        client.force_login(presenter_user)
        assert client.get(reverse("volunteer:index")).status_code == 200
        assert client.session[AGREED_KEY] is True
        # The profile row could vanish now and the session would carry on.
        PortalProfile.objects.filter(user=presenter_user).delete()
        assert client.get(reverse("volunteer:index")).status_code == 200
