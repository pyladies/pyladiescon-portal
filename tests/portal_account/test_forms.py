import json

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from portal_account.forms import PortalProfileForm
from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalProfileForm:
    def test_profile_form_saved(self, portal_user):
        form_data = {
            "user": portal_user,
            "first_name": "new fname",
            "last_name": "new lname",
            "pronouns": "pp",
        }
        form = PortalProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        form.save()

        portal_profile = PortalProfile.objects.get(user=portal_user)
        assert portal_profile.user == portal_user
        assert portal_profile.pronouns == form_data["pronouns"]
        assert portal_profile.user.first_name == form_data["first_name"]
        assert portal_profile.user.last_name == form_data["last_name"]

    def test_profile_form_required_fields(self, portal_user):
        form_data = {"user": portal_user}
        form = PortalProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()

        form_data = {"user": portal_user, "first_name": "new fname"}
        form = PortalProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()

        form_data = {"user": portal_user, "last_name": "new lname"}
        form = PortalProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()


@pytest.mark.django_db
class TestSignupView:
    def test_error_styling_on_invalid_signup(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "username": "",  # invalid empty username
                "email": "invalid-email",  # invalid email format
                "password1": "short",  # too short password
                "password2": "mismatch",  # password mismatch
            },
        )
        # styling classes
        assertContains(response, "is-invalid", status_code=200)
        assertContains(response, "invalid-feedback", status_code=200)
        # some specific messages
        assertContains(response, "This field is required", status_code=200)
        assertContains(response, "Enter a valid email address", status_code=200)

    def test_widget_tweaks_loaded(self, client):
        response = client.get(reverse("account_signup"))
        assertContains(response, "form-control", status_code=200)


# ---------- Sponsorship form coverage helpers ----------


@pytest.mark.django_db
class TestSponsorshipForm:
    def test_get_sponsorship_prices_json_returns_valid_json(self, monkeypatch):
        from sponsorship.forms import SponsorshipProfileForm
        from sponsorship.models import SponsorshipProfile

        fake_prices = {"Champion": "1000.00", "Supporter": "500.00"}

        # make the classmethod/staticmethod return a fixed dict for the test
        monkeypatch.setattr(
            SponsorshipProfile,
            "get_sponsorship_prices",
            staticmethod(lambda: fake_prices),
            raising=False,
        )

        form = SponsorshipProfileForm()
        payload = form.get_sponsorship_prices_json()
        assert isinstance(payload, str)
        assert json.loads(payload) == fake_prices

    def test_init_sets_attrs_and_amount_field_not_required(self):
        from sponsorship.forms import SponsorshipProfileForm

        form = SponsorshipProfileForm()

        st_attrs = form.fields["sponsorship_type"].widget.attrs
        assert st_attrs.get("class") == "form-control"
        assert st_attrs.get("id") == "id_sponsorship_type"

        amt_field = form.fields["amount_to_pay"]
        amt_attrs = amt_field.widget.attrs
        assert amt_attrs.get("class") == "form-control"
        assert amt_attrs.get("id") == "id_amount_to_pay"
        assert amt_attrs.get("step") == "0.01"
        assert amt_attrs.get("min") == "0"
        assert amt_field.required is False

    def test_clean_amount_to_pay_validation(self):
        from django import forms as djforms

        from sponsorship.forms import SponsorshipProfileForm

        form = SponsorshipProfileForm()

        # None -> error
        form.cleaned_data = {"amount_to_pay": None}
        with pytest.raises(djforms.ValidationError):
            form.clean_amount_to_pay()

        # <= 0 -> error
        form.cleaned_data = {"amount_to_pay": 0}
        with pytest.raises(djforms.ValidationError):
            form.clean_amount_to_pay()

        # positive -> ok, returned as-is
        form.cleaned_data = {"amount_to_pay": 10}
        assert form.clean_amount_to_pay() == 10
