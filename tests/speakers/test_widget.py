"""The website widget (task 6.3, design §11.2): readable source in
frontend/widget/v1.js, minified into the served portal/static/widget/v1.js
by `npm run build:widget`. Checked here for its budget, its freshness and
its contract; its behaviour is exercised in a browser against the API
(see speakers/README.md)."""

import hashlib
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.urls import reverse

from .factories import make_settings

SOURCE = Path(settings.BASE_DIR) / "frontend" / "widget" / "v1.js"
BUILT = Path(finders.find("widget/v1.js"))


def test_the_served_widget_stays_within_its_budget():
    assert BUILT.stat().st_size <= 15 * 1024


def test_the_served_widget_is_built_from_the_current_source():
    """Without Node in CI: the build stamps the source's sha256."""
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert (
        f"(sha256 {digest})" in BUILT.read_text().splitlines()[0]
    ), "frontend/widget/v1.js changed; run `npm run build:widget`"


def test_the_widget_loads_nothing_but_the_api():
    source = SOURCE.read_text()
    assert "import(" not in source
    assert "importScripts" not in source
    assert not re.search(r"\beval\(|new Function\(", source)
    assert len(re.findall(r"(?<![.\w])fetch\(", source)) == 1
    # The only markup it injects comes from the sanitized *_html fields.
    assert sorted(re.findall(r"\bhtml: ([^}]+)}", source)) == [
        "p.bio_html ",
        "s.summary_html ",
        's[k + "_html"] ',
    ]


def test_every_view_reads_a_built_endpoint():
    source = SOURCE.read_text()
    for path in ('"presenters/"', '"sessions/"'):
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
