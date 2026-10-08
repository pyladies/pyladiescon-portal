"""The Presenters page's data view and its CSV (speakers/directory.py)."""

import csv
import io
import re
import zipfile

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from speakers.directory import DATA_COLUMNS
from speakers.tables import PresenterDataTable
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

LIST = reverse("speakers:presenter_list")
CSV = reverse("speakers:presenter_data_csv")
ZIP = reverse("speakers:presenter_data_zip")
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
        assert "Download CSV" in content and "Collapse" in content
        assert not hasattr(response.context["table"], "page")  # unpaginated

    def test_the_default_is_the_basic_list(self, client, organizer, people):
        """Name, email, sessions one per line, Discord, the invitation's
        state, liaison; no links; Expand offered."""
        client.force_login(organizer)
        response = client.get(LIST)
        content = response.content.decode()
        assert response.context["view"] == "basic"
        assert "page-wide" not in content
        assert "ada_l" in content and "Lena" in content and "Django 101" in content
        assert re.search(r"<li><a [^>]+>Django 101</a>", content)  # a list item
        assert re.search(r">\s*Invitation\s*<", content)
        assert "github.com/ada" not in content and "Europe/London" not in content
        assert "Expand" in content and "?view=data" in content
        assert "?view=invitations" not in content and "Account" not in content
        nonsense = client.get(LIST, {"view": "nonsense"})
        assert nonsense.context["view"] == "basic"

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
        assert ada[11:] == ["no", "no", "Django 101 (Moderator)", "", "Lena"]
        # A name that would read as a formula is kept as text.
        assert grace[0] == "'=Grace"
        assert grace[13] == "" and grace[14] == ""
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


@pytest.mark.django_db
class TestPackage:
    def test_csv_photos_and_readme(self, client, organizer, people, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        ada = people["ada"]
        ada.headshot.save("Ada Photo.PNG", SimpleUploadedFile("x.png", PNG))
        client.force_login(organizer)
        response = client.get(ZIP)
        assert response["Content-Type"] == "application/zip"
        assert 'filename="presenters-2025.zip"' in response["Content-Disposition"]
        assert response.streaming
        archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
        assert sorted(archive.namelist()) == [
            "README.txt",
            f"photos/{ada.slug}.png",
            "presenters.csv",
        ]
        rows = list(csv.reader(io.StringIO(archive.read("presenters.csv").decode())))
        assert rows[0] == [header for header, _ in DATA_COLUMNS] + ["Photo file"]
        assert rows[1][0] == "Ada" and rows[1][-1] == f"{ada.slug}.png"
        assert rows[2][0] == "'=Grace" and rows[2][-1] == ""
        assert archive.read(f"photos/{ada.slug}.png") == PNG
        # Stored, not recompressed: the bytes are already compressed.
        assert (
            archive.getinfo(f"photos/{ada.slug}.png").compress_type
            == zipfile.ZIP_STORED
        )
        assert "never go on the public site" in archive.read("README.txt").decode()

    def test_filters_and_scope_apply(self, client, liaison, people):
        client.force_login(liaison)
        content = b"".join(client.get(ZIP).streaming_content)
        archive = zipfile.ZipFile(io.BytesIO(content))
        rows = list(csv.reader(io.StringIO(archive.read("presenters.csv").decode())))
        assert [row[0] for row in rows[1:]] == ["Ada"]

    def test_the_data_view_offers_it(self, client, organizer, people):
        client.force_login(organizer)
        content = client.get(LIST, {"view": "data", "search": "ada"}).content.decode()
        assert f'href="{ZIP}?search=ada"' in content


@pytest.mark.django_db
class TestScale:
    """A hundred speakers: the page, the CSV and the zip read the edition in
    a fixed number of queries, however many rows there are."""

    def grow(self, conference, liaison, n):
        for i in range(n):
            presenter = make_presenter(
                conference, display_name=f"Extra {i}", liaison=liaison
            )
            session = make_session(conference, title=f"Talk {i}", kind="TALK")
            add_presenter(session, presenter)

    def queries(self, client, url, params=None):
        with CaptureQueriesContext(connection) as context:
            response = client.get(url, params or {})
            if response.streaming:
                b"".join(response.streaming_content)
        return len(context)

    def test_queries_stay_flat(self, client, organizer, liaison, people, conference):
        client.force_login(organizer)
        before = [
            self.queries(client, LIST, {"view": "data"}),
            self.queries(client, CSV),
            self.queries(client, ZIP),
        ]
        self.grow(conference, liaison, 12)
        after = [
            self.queries(client, LIST, {"view": "data"}),
            self.queries(client, CSV),
            self.queries(client, ZIP),
        ]
        assert after == before
        response = client.get(LIST, {"view": "data"})
        assert len(response.context["table"].rows) == 14  # every row, one page
