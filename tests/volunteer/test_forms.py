import pytest

from volunteer.forms import VolunteerProfileForm
from volunteer.models import VolunteerProfile


@pytest.mark.django_db
class TestVolunteerProfileForm:

    def test_profile_form_saved(self, portal_user):

        form_data = {
            "user": portal_user,
            "languages_spoken": ["en"],
            "timezone": "UTC-12",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        form.save()

        volunteer_profile = VolunteerProfile.objects.get(user=portal_user)
        assert volunteer_profile.user == portal_user

    def test_profile_form_required_fields(self, portal_user):
        form_data = {"user": portal_user}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()

        form_data = {
            "user": portal_user,
            "languages_spoken": ["en"],
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()

        form_data = {
            "user": portal_user,
            "timezone": "UTC-12",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
