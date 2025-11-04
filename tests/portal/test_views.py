import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile
from volunteer.models import PyladiesChapter


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


@pytest.mark.django_db
class TestPortalStats:

    def test_stats_doesnt_require_login(self, client):
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200
        assert "PyLadiesCon Stats" in response.content.decode()


@pytest.mark.django_db
class TestPyladiesChapters:

    def test_view_pyladies_chapters_is_public(self, client):
        response = client.get(reverse("chapters"))
        assert response.status_code == 200
        assert "PyLadies Chapters" in response.content.decode()

    def test_view_pyladies_chapters_displays_chapters(self, client):
        chapter_1 = PyladiesChapter.objects.create(
            chapter_name="vancouver",
            chapter_description="Vancouver, Canada",
            chapter_website="https://vancouver.pyladies.com/",
        )
        chapter_2 = PyladiesChapter.objects.create(
            chapter_name="berlin", chapter_description="Berlin, Germany"
        )

        response = client.get(reverse("chapters"))
        assert response.status_code == 200
        assert chapter_1.chapter_name in response.content.decode()
        assert chapter_2.chapter_name in response.content.decode()
        assert chapter_1.chapter_description in response.content.decode()
        assert chapter_2.chapter_description in response.content.decode()
        assert chapter_1.chapter_website in response.content.decode()
