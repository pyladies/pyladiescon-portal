"""Which hub a page belongs to (portal/navigation.py).

The mapping is data, so the risk is a page nobody added to it: it then
marks Home while the reader is mid-flow somewhere else. The census below
walks every URL in the speaker, volunteer, sponsorship and organizer
groups and fails on one that answers "home".
"""

import pytest
from django.urls import get_resolver

from portal.navigation import HOME, ORGANIZE, SPEAKING, VOLUNTEER, current_section


class FakeMatch:
    def __init__(self, view_name):
        self.view_name = view_name
        self.namespaces = view_name.split(":")[:-1]


class FakeRequest:
    def __init__(self, view_name=None):
        if view_name is not None:
            self.resolver_match = FakeMatch(view_name)


def section_of(view_name):
    return current_section(FakeRequest(view_name))


def named_urls():
    """Every named URL pattern, as "namespace:name" or "name"."""
    resolver = get_resolver()
    names = []

    def walk(patterns, prefix):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                namespace = pattern.namespace
                walk(
                    pattern.url_patterns,
                    f"{prefix}{namespace}:" if namespace else prefix,
                )
            elif pattern.name:
                names.append(f"{prefix}{pattern.name}")

    walk(resolver.url_patterns, "")
    return names


def test_a_request_that_matched_nothing_is_home():
    assert current_section(FakeRequest()) == HOME


@pytest.mark.parametrize(
    "view_name,expected",
    [
        ("index", HOME),
        ("chapters", HOME),
        ("volunteer:index", VOLUNTEER),
        ("my_teams", VOLUNTEER),
        ("team_dashboard", VOLUNTEER),
        ("organizer_dashboard", ORGANIZE),
        ("start_new_year", ORGANIZE),
        ("teams", ORGANIZE),
        ("speakers:session_list", ORGANIZE),
        ("speakers:my_dashboard", SPEAKING),
        ("speakers:my_checklist", SPEAKING),
        # A person's own work sits under My volunteering, whoever they are.
        ("speakers:checklist_queue", VOLUNTEER),
        ("speakers:item_detail", VOLUNTEER),
        # Sponsors: the list is the read-only page in the personal rail,
        # the editing pages are organizer ones.
        ("sponsorship:sponsorship_list", VOLUNTEER),
        ("sponsorship:tier_list", ORGANIZE),
    ],
)
def test_sections(view_name, expected):
    assert section_of(view_name) == expected


def test_every_hub_url_names_a_hub():
    """A page in one of the four groups that answers "home" is a page whose
    tab would go quiet mid-flow. Add it to the mapping."""
    stray = [
        name
        for name in named_urls()
        if name.split(":")[0] in {"speakers", "volunteer", "sponsorship"}
        and section_of(name) == HOME
    ]
    assert stray == []


def test_the_organizer_pages_outside_those_namespaces_are_mapped():
    for name in (
        "organizer_dashboard",
        "conference_list",
        "conference_new",
        "start_new_year",
        "teams",
        "team_new",
        "maintenance_accounts",
    ):
        assert section_of(name) == ORGANIZE, name
