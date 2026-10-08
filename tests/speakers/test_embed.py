"""The iframe embed (task 6.4, design §11.2)."""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import ProgramVisibility
from speakers.models import SpeakerSettings
from speakers.public import preview_token

from .factories import make_settings


def embed(view="schedule", conference="2025"):
    return reverse("speakers_embed:embed", args=[conference, view])


@pytest.fixture
def settings_row(conference):
    return make_settings(conference, program_visibility=ProgramVisibility.PUBLISHED)


def go_internal(settings_row):
    settings_row.program_visibility = ProgramVisibility.INTERNAL
    settings_row.save(update_fields=["program_visibility"])


@pytest.mark.django_db
class TestEmbedPage:
    @pytest.mark.parametrize("view", ["schedule", "sessions", "speakers"])
    def test_a_bare_page_with_the_widget(self, client, settings_row, view):
        response = client.get(embed(view))
        assert response.status_code == 200
        content = response.content.decode()
        assert f'data-pyladiescon-widget="{view}"' in content
        assert 'data-conference="2025"' in content
        assert re.search(r"/static/widget/v1(\.\w+)?\.js", content)
        assert re.search(r"/static/js/embed-frame(\.\w+)?\.js", content)
        assert "navbar" not in content  # no portal chrome

    def test_other_sites_may_frame_it(self, client, settings_row):
        response = client.get(embed())
        assert "X-Frame-Options" not in response
        assert response["Cache-Control"] == "public, max-age=300"
        junk = client.get(embed(), {"preview": "anything"})
        assert junk["Cache-Control"] == "public, max-age=300"
        token = preview_token(SpeakerSettings.objects.get(conference__slug="2025"))
        go_internal(settings_row)
        assert client.get(embed(), {"preview": token})["Cache-Control"] == "no-store"

    def test_an_accent_colour_and_nothing_else(self, client, settings_row):
        good = client.get(embed(), {"accent": "#c2185b"}).content.decode()
        assert 'style="--plc-accent: #c2185b"' in good
        for bad in ("red;background:url(x)", "#abcde", "#abcdefg"):
            content = client.get(embed(), {"accent": bad}).content.decode()
            assert "--plc-accent" not in content, bad
        short = client.get(embed(), {"accent": "#c215"}).content.decode()
        assert 'style="--plc-accent: #c215"' in short

    def test_unknown_things_are_404(self, client, settings_row, conference):
        assert client.get(embed("calendar")).status_code == 404
        assert client.get(embed(conference="1999")).status_code == 404
        SpeakerSettings.objects.filter(pk=settings_row.pk).update(
            speaker_module_enabled=False
        )
        assert client.get(embed()).status_code == 404

    def test_the_share_tab_offers_the_iframe(self, client, settings_row):
        organizer = User.objects.create_user(
            username="organizer", email="org@example.com", is_staff=True
        )
        client.force_login(organizer)
        content = client.get(reverse("speakers:program_share")).content.decode()
        assert "http://testserver/embed/2025/schedule/" in content
        assert "pyladiescon-embed" in content
        assert "event.origin !== &quot;http://testserver&quot;" in content

    def test_the_iframe_title_is_escaped(self, client, settings_row, conference):
        conference.name = 'Py"Con <2025>'
        conference.save()
        organizer = User.objects.create_user(
            username="organizer", email="org@example.com", is_staff=True
        )
        client.force_login(organizer)
        content = client.get(reverse("speakers:program_share")).content.decode()
        # The snippet is escaped for its attribute, then once more by the
        # template inside the textarea, so the quote reads as &amp;quot; here.
        assert (
            "title=&quot;Py&amp;quot;Con &amp;lt;2025&amp;gt; schedule&quot;" in content
        )
