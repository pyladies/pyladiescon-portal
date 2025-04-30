import pytest

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
            "coc_agreement": True,
        }
        form = PortalProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        form.save()

        portal_profile = PortalProfile.objects.get(user=portal_user)
        assert portal_profile.user == portal_user
        assert portal_profile.pronouns == form_data["pronouns"]
        assert portal_profile.coc_agreement is True
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
