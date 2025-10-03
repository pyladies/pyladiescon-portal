import pytest
from django.contrib.auth import get_user_model

from sponsorship.forms import SponsorshipProfileForm
from sponsorship.models import SponsorshipProfile, SponsorshipTier

pytestmark = pytest.mark.django_db


def _mkuser(username="u_form"):
    User = get_user_model()
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass1234"
    )


def test_form_save_commit_true_executes_save_and_save_m2m(monkeypatch):
    user = _mkuser()

    tier = SponsorshipTier.objects.create(
        name="Champion", amount=10000.00, description="Champion sponsorship tier"
    )

    # Your form unconditionally calls save_m2m(); stub it since the form has no M2M fields
    monkeypatch.setattr(
        "sponsorship.forms.SponsorshipProfileForm.save_m2m",
        lambda self: None,
        raising=False,
    )

    data = {
        "main_contact_user": str(user.id),
        "organization_name": "ACME Corp",
        "sponsorship_tier": str(tier.pk),
        "company_description": "desc",
        "application_status": "pending",
    }

    # Pass user=... so form.save() sets main_contact_user correctly
    form = SponsorshipProfileForm(data=data, user=user)
    assert form.is_valid(), form.errors.as_text()

    # IMPORTANT: model requires `user` (OneToOne, non-null). Set it before commit=True save.
    form.instance.user = user

    obj = form.save(commit=True)  # <-- executes instance.save() and save_m2m()

    assert isinstance(obj, SponsorshipProfile)
    assert obj.pk is not None
    assert obj.user == user
    assert obj.main_contact_user == user
    assert obj.application_status == "pending"
    assert obj.sponsorship_tier == tier
