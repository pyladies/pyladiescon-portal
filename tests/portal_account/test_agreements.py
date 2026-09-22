"""The Code of Conduct and Terms of Service gate.

Signup collects both agreements, but an account can arrive without ever
meeting that form: a speaker invitation creates one and signs the person in,
and a sign-in code lets them back in afterwards. These tests use the
``no_agreements`` marker, so the real predicate runs rather than the
suite-wide stand-in in ``conftest.py``.
"""

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.agreements import (
    AgreementRequiredMiddleware,
    agreement_url_for,
    has_agreed,
)
from portal_account.models import PortalProfile
from speakers.models import Presenter
from tests.speakers.factories import make_settings

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
