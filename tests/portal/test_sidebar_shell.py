"""Stage A: the sidebar shell foundation.

The two-column rail is opt-in. Pages that only fill ``content`` (the vast
majority) render full-width with no rail markup; pages that extend
``portal/base_sidebar.html`` get a pinned-on-desktop / drawer-on-mobile rail.
"""

import re

import pytest
from django.template import engines
from django.urls import reverse

from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile


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


def _nav(html):
    """The top navigation list, so a test can ask which tab is current
    without matching the rest of the page."""
    return html.split('id="navbarsExample04"')[1].split("</ul>")[0]


def _current(nav):
    """The label of the tab marked as the current page, or None."""
    match = re.search(r'aria-current="page"[^>]*>([^<]+)<', nav)
    return match.group(1).strip() if match else None


@pytest.mark.django_db
class TestTopNavSections:
    """The top nav marks the hub the page belongs to, in the accessibility
    tree as well as in colour, and shows one tab per hub."""

    def test_a_page_outside_every_hub_marks_home(self, client, portal_user, conference):
        client.force_login(portal_user)
        nav = _nav(client.get(reverse("chapters")).content.decode())
        assert _current(nav) == "Home"

    def test_each_hub_marks_its_own_tab(
        self, client, admin_user, portal_user, conference
    ):
        client.force_login(admin_user)
        nav = _nav(client.get(reverse("organizer_dashboard")).content.decode())
        assert _current(nav) == "Organize"
        # An Organize page that is not the dashboard keeps the same tab.
        nav = _nav(client.get(reverse("conference_list")).content.decode())
        assert _current(nav) == "Organize"
        client.force_login(portal_user)
        nav = _nav(client.get(reverse("volunteer:index")).content.decode())
        assert _current(nav) == "Volunteer"

    def test_the_mark_is_in_the_accessibility_tree(
        self, client, admin_user, conference
    ):
        """Not colour alone, and not a stylesheet feature: the anchor says
        which tab is current, the way the rail and the breadcrumbs do."""
        client.force_login(admin_user)
        nav = _nav(client.get(reverse("organizer_dashboard")).content.decode())
        assert nav.count('aria-current="page"') == 1
        assert "nav-link active" in nav

    def test_no_sponsorship_tab_for_anyone(
        self, client, admin_user, portal_user, conference
    ):
        """Organizers have Sponsors in the Organize rail, approved volunteers
        in their personal rail; the top nav carries neither."""
        sponsorship = reverse("sponsorship:sponsorship_list")
        client.force_login(admin_user)
        html = client.get(reverse("organizer_dashboard")).content.decode()
        nav = html.split('id="navbarsExample04"')[1].split("</ul>")[0]
        assert sponsorship not in nav and sponsorship in html
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        client.force_login(portal_user)
        html = client.get(reverse("volunteer:index")).content.decode()
        nav = html.split('id="navbarsExample04"')[1].split("</ul>")[0]
        assert sponsorship not in nav
        rail = html.split('id="appSidebar"')[1]
        assert sponsorship in rail and "Sponsors" in rail
        # A volunteer who is not approved gets neither.
        VolunteerProfile.objects.filter(user=portal_user).update(
            application_status=ApplicationStatus.PENDING
        )
        html = client.get(reverse("volunteer:index")).content.decode()
        assert sponsorship not in html
