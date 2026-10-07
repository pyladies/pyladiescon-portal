"""The website widget (task 6.3, design §11.2): a static script, checked
here for its budget and its contract; its behaviour is exercised in a
browser against the API (see speakers/README.md)."""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.urls import reverse

from .factories import make_settings

WIDGET = Path(finders.find("widget/v1.js"))


def test_the_widget_stays_within_its_budget():
    assert WIDGET.stat().st_size <= 15 * 1024


def test_the_widget_loads_nothing_but_the_api():
    source = WIDGET.read_text()
    assert "import(" not in source
    assert "importScripts" not in source
    assert not re.search(r"\beval\(|new Function\(", source)
    assert len(re.findall(r"(?<![.\w])fetch\(", source)) == 1
    # The only markup it injects comes from the sanitized *_html fields.
    assert re.findall(r"html: ([^}]+)}", source) == [
        's[k + "_html"] ',
        "p.bio_html ",
    ]


def test_every_view_reads_a_built_endpoint():
    source = WIDGET.read_text()
    for path in ('"presenters/"', '"sessions/"', '"schedule.ics?sessions="'):
        assert path in source


@pytest.mark.django_db
def test_the_publishing_page_offers_the_snippet(client, conference):
    make_settings(conference)
    organizer = User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )
    client.force_login(organizer)
    content = client.get(reverse("speakers:program_publishing")).content.decode()
    assert "data-pyladiescon-widget=&quot;schedule&quot;" in content
    assert "data-conference=&quot;2025&quot;" in content
    assert "http://testserver/static/widget/v1.js" in content
