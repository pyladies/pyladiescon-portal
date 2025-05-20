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
class TestPortalProfileFormAgreements:
    def test_agreements_disabled_when_both_true(self, portal_user):
        portal_profile, _ = PortalProfile.objects.get_or_create(
            user=portal_user, defaults={"coc_agreement": True, "tos_agreement": True}
        )
        portal_profile.coc_agreement = True
        portal_profile.tos_agreement = True
        portal_profile.save()

        form = PortalProfileForm(user=portal_user, instance=portal_profile)

        assert form.fields["coc_agreement"].disabled is True
        assert form.fields["tos_agreement"].disabled is True

    def test_agreements_not_disabled_when_not_both_true(self, portal_user):
        portal_profile, _ = PortalProfile.objects.get_or_create(user=portal_user)

        portal_profile.coc_agreement = True
        portal_profile.tos_agreement = False
        portal_profile.save()

        form = PortalProfileForm(user=portal_user, instance=portal_profile)
        assert form.fields["coc_agreement"].disabled is False
        assert form.fields["tos_agreement"].disabled is False

        portal_profile.coc_agreement = False
        portal_profile.tos_agreement = True
        portal_profile.save()

        form = PortalProfileForm(user=portal_user, instance=portal_profile)
        assert form.fields["coc_agreement"].disabled is False
        assert form.fields["tos_agreement"].disabled is False

        portal_profile.coc_agreement = False
        portal_profile.tos_agreement = False
        portal_profile.save()

        form = PortalProfileForm(user=portal_user, instance=portal_profile)
        assert form.fields["coc_agreement"].disabled is False
        assert form.fields["tos_agreement"].disabled is False

    def test_agreements_not_disabled_for_new_profile(self, portal_user):
        PortalProfile.objects.filter(user=portal_user).delete()

        form = PortalProfileForm(user=portal_user)
        assert form.fields["coc_agreement"].disabled is False
        assert form.fields["tos_agreement"].disabled is False


@pytest.mark.django_db
class TestSignupView:
    def test_error_styling_on_invalid_signup(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "username": "",  # Invalid empty username
                "email": "invalid-email",  # Invalid email format
                "password1": "short",  # Too short password
                "password2": "mismatch",  # Password mismatch
            },
        )

        # Verify error styling classes exist
        assertContains(
            response, "is-invalid", status_code=200
        )  # Bootstrap invalid class
        assertContains(
            response, "invalid-feedback", status_code=200
        )  # Error message class

        # Verify specific field errors
        assertContains(response, "This field is required", status_code=200)  # username
        assertContains(
            response, "Enter a valid email address", status_code=200
        )  # email

    def test_widget_tweaks_loaded(self, client):
        response = client.get(reverse("account_signup"))
        assertContains(
            response, "form-control", status_code=200
        )  # Verify Bootstrap styling
