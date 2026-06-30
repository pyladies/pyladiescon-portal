"""Stage A: the sidebar shell foundation.

The two-column rail is opt-in. Pages that only fill ``content`` (the vast
majority) render full-width with no rail markup; pages that extend
``portal/base_sidebar.html`` get a pinned-on-desktop / drawer-on-mobile rail.
"""

import pytest
from django.template import engines


def _render(template_string):
    return engines["django"].from_string(template_string).render({})


@pytest.mark.django_db
class TestSidebarShell:
    def test_plain_page_has_no_rail(self):
        # Extending base.html and filling only content stays full-width.
        html = _render(
            '{% extends "portal/base.html" %}'
            "{% block content %}Just content{% endblock %}"
        )
        assert "Just content" in html
        assert 'id="appSidebar"' not in html
        assert "offcanvas-md" not in html

    def test_sidebar_page_renders_pinned_drawer_rail(self):
        html = _render(
            '{% extends "portal/base_sidebar.html" %}'
            "{% block sidebar_title %}My App{% endblock %}"
            '{% block sidebar %}<a href="/x">Item</a>{% endblock %}'
            "{% block content %}Body here{% endblock %}"
        )
        # Rail present, content present.
        assert 'id="appSidebar"' in html
        assert "My App" in html
        assert "Body here" in html
        # offcanvas-md = static at md+, drawer below; the toggle drives it.
        assert "offcanvas-md" in html
        assert 'data-bs-toggle="offcanvas"' in html
        assert 'data-bs-target="#appSidebar"' in html

    def test_sidebar_item_include_marks_active(self):
        html = _render(
            '{% include "portal/_sidebar_item.html" with url="/inbox" '
            'label="Inbox" icon="fa-inbox" active=True badge=3 %}'
        )
        assert 'href="/inbox"' in html
        assert "Inbox" in html
        assert "active" in html
        assert 'aria-current="page"' in html
        assert "fa-inbox" in html
        assert "3" in html  # the badge

    def test_sidebar_item_inactive_has_no_active_marker(self):
        html = _render(
            '{% include "portal/_sidebar_item.html" with url="/sent" '
            'label="Sent" active=False %}'
        )
        assert 'href="/sent"' in html
        assert 'aria-current="page"' not in html
