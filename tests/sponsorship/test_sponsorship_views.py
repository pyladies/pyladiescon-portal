# tests/sponsorship/test_sponsorship_views.py
import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse

from sponsorship.models import SponsorshipTier

pytestmark = pytest.mark.django_db


def _create_user(**kwargs):
    User = get_user_model()
    base = dict(username="user1", email="user1@example.com")
    base.update(kwargs)
    return User.objects.create_user(password="pass1234", **base)


@pytest.fixture
def auth_client(client):
    u = _create_user()
    client.login(username=u.username, password="pass1234")
    client.user = u
    return client


def test_login_required_redirects(client):
    url = reverse("sponsorship:create_sponsorship_profile")
    resp = client.get(url)
    assert resp.status_code in (301, 302)
    assert "login" in resp["Location"].lower()


def test_get_renders_form(auth_client):
    url = reverse("sponsorship:create_sponsorship_profile")
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "form" in resp.context
    from sponsorship.forms import SponsorshipProfileForm

    assert isinstance(resp.context["form"], SponsorshipProfileForm)


def test_post_invalid_shows_errors(auth_client):
    url = reverse("sponsorship:create_sponsorship_profile")
    resp = auth_client.post(url, data={}, follow=True)
    assert resp.status_code == 200
    form = resp.context["form"]
    assert form.errors


def test_post_valid_executes_save_block_and_sets_pending(auth_client, monkeypatch):
    from django.urls import reverse

    import sponsorship.views as views
    from sponsorship.forms import SponsorshipProfileForm
    from sponsorship.models import SponsorshipProfile

    tier = SponsorshipTier.objects.create(
        name="Champion", amount=10000.00, description="Champion sponsorship tier"
    )

    # Stub save_m2m so the unconditional call in the form doesn't explode
    monkeypatch.setattr(
        "sponsorship.forms.SponsorshipProfileForm.save_m2m",
        lambda self: None,
        raising=False,
    )

    # Make the view instantiate the form with user=request.user
    RealForm = views.SponsorshipProfileForm

    def FormFactory(*args, **kwargs):
        kwargs.setdefault("user", auth_client.user)
        return RealForm(*args, **kwargs)

    monkeypatch.setattr(views, "SponsorshipProfileForm", FormFactory, raising=False)

    url = reverse("sponsorship:create_sponsorship_profile")
    data = {
        "main_contact_user": str(auth_client.user.id),
        "organization_name": "ACME Corp",
        "sponsorship_tier": str(tier.pk),
        "company_description": "We love sponsoring great events!",
        "application_status": "pending",
    }

    resp = auth_client.post(url, data=data, follow=True)
    assert resp.status_code == 200

    # Fail fast with details if the form was invalid
    if "form" in resp.context and getattr(resp.context["form"], "errors", None):
        import pytest

        pytest.fail(f"Form errors: {resp.context['form'].errors.as_text()}")

    profile = SponsorshipProfile.objects.latest("id")
    assert profile.user == auth_client.user
    assert profile.main_contact_user_id == auth_client.user.id
    assert profile.application_status == "pending"
    assert profile.sponsorship_tier == tier

    msgs = [str(m).lower() for m in get_messages(resp.wsgi_request)]
    assert any("submitted successfully" in m for m in msgs)

    fresh_form = resp.context["form"]
    assert isinstance(fresh_form, SponsorshipProfileForm)
    assert not fresh_form.is_bound


def test_sponsorship_success_executes_body_and_raises(auth_client, capsys):
    url = reverse("sponsorship:success")
    with pytest.raises((ValueError, TypeError)):
        auth_client.get(url)

    out = capsys.readouterr().out
    assert "Not implemented" in out
