"""The Presenters page's data view and its CSV (speakers/directory.py)."""

import csv
import io
import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.directory import DATA_COLUMNS
from speakers.tables import PresenterDataTable
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

LIST = reverse("speakers:presenter_list")
CSV = reverse("speakers:presenter_data_csv")


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


@pytest.fixture
def liaison(db, conference):
    user = User.objects.create_user(
        username="liaison", email="liaison@example.com", first_name="Lena"
    )
    VolunteerProfile.objects.create(
        user=user,
        conference=conference,
        application_status=ApplicationStatus.APPROVED,
    )
    return user


@pytest.fixture
def people(conference, liaison):
    make_settings(conference)
    panel = make_session(conference, title="Django 101", kind="PANEL")
    ada = make_presenter(
        conference,
        display_name="Ada",
        email="ada@example.com",
        pronouns="she/her",
        discord_username="ada_l",
        timezone="Europe/London",
        location="London",
        website_url="https://ada.example/",
        github_username="ada",
        mastodon_url="https://fosstodon.org/@ada",
        linkedin_url="https://www.linkedin.com/in/ada/",
        bluesky_username="ada.example",
        liaison=liaison,
        is_public=False,
    )
    add_presenter(panel, ada, role="MODERATOR")
    grace = make_presenter(conference, display_name="=Grace", email="grace@example.com")
    return {"ada": ada, "grace": grace, "panel": panel}


def rows_of(response):
    return list(csv.reader(io.StringIO(response.content.decode())))


@pytest.mark.django_db
class TestDataView:
    def test_the_table_and_the_csv_share_their_columns(self):
        headers = [column.header for column in PresenterDataTable([]).columns]
        assert headers == [header for header, _ in DATA_COLUMNS]

    def test_everything_the_team_looks_up(self, client, organizer, people):
        client.force_login(organizer)
        response = client.get(LIST, {"view": "data"})
        content = response.content.decode()
        assert response.context["data_view"] is True
        assert "page-wide" in content  # full width, no rail
        assert 'href="https://github.com/ada"' in content
        assert 'href="https://bsky.app/profile/ada.example"' in content
        assert "ada_l" in content and "Europe/London" in content
        cells = re.findall(r"<td[^>]*>\s*no\s*</td>", content)
        assert len(cells) >= 2  # photo and public profile, for Ada
        assert "Django 101" in content and "Moderator" in content
        assert "Lena" in content
        assert "Download CSV" in content and "Invitations view" in content
        assert not hasattr(response.context["table"], "page")  # unpaginated

    def test_the_default_view_is_still_about_invitations(
        self, client, organizer, people
    ):
        client.force_login(organizer)
        response = client.get(LIST)
        content = response.content.decode()
        assert response.context["data_view"] is False
        assert "page-wide" not in content
        assert "ada_l" not in content
        assert "?view=data" in content

    def test_the_csv_matches_the_rows_and_the_filters(self, client, organizer, people):
        client.force_login(organizer)
        response = client.get(CSV)
        assert response["Content-Type"] == "text/csv"
        assert 'filename="presenters-2025.csv"' in response["Content-Disposition"]
        rows = rows_of(response)
        assert rows[0] == [header for header, _ in DATA_COLUMNS]
        ada, grace = rows[1], rows[2]
        assert ada[:6] == [
            "Ada",
            "she/her",
            "ada@example.com",
            "ada_l",
            "Europe/London",
            "London",
        ]
        assert ada[6:11] == [
            "https://ada.example/",
            "ada",
            "https://fosstodon.org/@ada",
            "https://www.linkedin.com/in/ada/",
            "ada.example",
        ]
        assert ada[11:] == ["no", "no", "Django 101 (Moderator)", "Lena"]
        # A name that would read as a formula is kept as text.
        assert grace[0] == "'=Grace"
        assert grace[13] == ""
        filtered = rows_of(client.get(CSV, {"search": "grace@"}))
        assert [row[0] for row in filtered[1:]] == ["'=Grace"]

    def test_a_liaison_sees_and_downloads_their_own_only(self, client, liaison, people):
        client.force_login(liaison)
        response = client.get(LIST, {"view": "data"})
        assert [p.display_name for p in response.context["table"].data] == ["Ada"]
        rows = rows_of(client.get(CSV))
        assert [row[0] for row in rows[1:]] == ["Ada"]

    def test_the_toggle_keeps_the_filters(self, client, organizer, people):
        client.force_login(organizer)
        content = client.get(LIST, {"search": "ada", "page": "1"}).content.decode()
        assert "?view=data&search=ada" in content
        content = client.get(LIST, {"view": "data", "search": "ada"}).content.decode()
        assert f'href="{CSV}?search=ada"' in content
        assert f'href="{LIST}?search=ada"' in content
