"""Stage A: the sidebar shell foundation.

The two-column rail is opt-in. Pages that only fill ``content`` (the vast
majority) render full-width with no rail markup; pages that extend
``portal/base_sidebar.html`` get a pinned-on-desktop / drawer-on-mobile rail.
"""

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


@pytest.mark.django_db
class TestTopNavSections:
    """The top nav marks the section whose rail is on the page, and shows one
    tab per hub: Sponsorship only for viewers who are not organizers."""

    def test_no_hard_coded_active_tab(self, client, portal_user, conference):
        client.force_login(portal_user)
        html = client.get(reverse("chapters")).content.decode()
        assert 'class="nav-link active"' not in html
        assert 'data-nav-section="home"' in html
        assert "data-rail-section" not in html  # no rail: Home is current

    def test_rails_name_their_section(
        self, client, admin_user, portal_user, conference
    ):
        client.force_login(admin_user)
        html = client.get(reverse("organizer_dashboard")).content.decode()
        assert 'data-rail-section="organize"' in html
        assert 'data-nav-section="organize"' in html
        client.force_login(portal_user)
        html = client.get(reverse("volunteer:index")).content.decode()
        assert 'data-rail-section="volunteer"' in html
        assert 'data-nav-section="volunteer"' in html

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
