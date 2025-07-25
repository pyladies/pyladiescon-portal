import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalIndex:

    def test_index_unauthenticated(self, client):

        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign up" in response.content.decode()
        assert "Login" in response.content.decode()

    def test_index_authenticated_no_profile_created(self, client, portal_user):

        client.force_login(portal_user)
        response = client.get(reverse("index"), follow=True)

        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()
        assertRedirects(response, reverse("portal_account:portal_profile_new"))

    def test_index_authenticated_profile_already_created(self, client, portal_user):

        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()
