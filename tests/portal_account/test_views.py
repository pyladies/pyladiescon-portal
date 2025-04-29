import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects


@pytest.mark.django_db
class TestPortalAccountIndex:

    def test_index_unauthenticated(self, client):

        response = client.get(reverse("portal_account:index"))
        assertRedirects(response, reverse("account_login") + "?next=/portal_account/")
