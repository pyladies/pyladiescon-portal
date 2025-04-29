import pytest
from django.urls import reverse

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalProfileModel:

    def test_profile_url(self, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()

        assert profile.get_absolute_url() == reverse(
            "portal_account:portal_profile_edit", kwargs={"pk": profile.pk}
        )

    def test_profile_str_representation(self, portal_user):
        profile = PortalProfile(user=portal_user)

        assert str(profile) == portal_user.username
