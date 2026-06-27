import pytest

from portal.context_processors import active_conference
from portal.models import Conference


@pytest.fixture(autouse=True)
def conference():
    """Override the global autouse fixture: these tests create their own
    Conference rows (specific years, active toggles), so no shared row is
    seeded here."""
    return None


@pytest.mark.django_db
class TestConferenceModel:
    def test_str(self):
        conference = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        assert str(conference) == "PyLadiesCon 2025"

    def test_defaults(self):
        """Fields fall back to their documented defaults."""
        conference = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        assert conference.is_active is False
        assert conference.pretix_event_slug == ""
        assert conference.sponsorship_goal == 0
        assert conference.donation_goal == 0
        assert conference.proposals_count == 0
        assert conference.volunteer_application_open is False
        assert conference.sponsorship_open is False
        assert conference.accepting_donations is True
        assert conference.start_date is None
        assert conference.end_date is None
        assert conference.banner_text == ""
        assert conference.historical_snapshot == {}

    def test_get_active_returns_none_when_no_active(self):
        Conference.objects.create(year=2025, name="PyLadiesCon 2025", slug="2025")
        assert Conference.get_active() is None

    def test_get_active_returns_active_conference(self):
        Conference.objects.create(year=2024, name="PyLadiesCon 2024", slug="2024")
        active = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025", is_active=True
        )
        assert Conference.get_active() == active

    def test_single_active_enforcer_on_create(self):
        """Activating a new conference deactivates any previously active one."""
        first = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024", is_active=True
        )
        second = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025", is_active=True
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.is_active is False
        assert second.is_active is True
        assert Conference.objects.filter(is_active=True).count() == 1

    def test_single_active_enforcer_on_update(self):
        """Flipping an inactive conference to active deactivates the other."""
        first = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024", is_active=True
        )
        second = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025", is_active=False
        )

        second.is_active = True
        second.save()

        first.refresh_from_db()
        assert first.is_active is False
        assert Conference.get_active() == second

    def test_saving_inactive_conference_keeps_active_untouched(self):
        """Re-saving an inactive row must not clear the active conference."""
        active = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025", is_active=True
        )
        inactive = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024", is_active=False
        )

        inactive.banner_text = "See you next year"
        inactive.save()

        active.refresh_from_db()
        assert active.is_active is True

    def test_ordering_most_recent_first(self):
        Conference.objects.create(year=2024, name="PyLadiesCon 2024", slug="2024")
        Conference.objects.create(year=2026, name="PyLadiesCon 2026", slug="2026")
        Conference.objects.create(year=2025, name="PyLadiesCon 2025", slug="2025")
        years = list(Conference.objects.values_list("year", flat=True))
        assert years == [2026, 2025, 2024]


@pytest.mark.django_db
class TestActiveConferenceContextProcessor:
    def test_returns_active_conference(self):
        active = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025", is_active=True
        )
        assert active_conference(None) == {"active_conference": active}

    def test_returns_none_when_no_active(self):
        assert active_conference(None) == {"active_conference": None}


@pytest.mark.django_db
class TestCloneTeamsFrom:
    def test_copies_team_structure_but_not_leads(self):
        from django.contrib.auth import get_user_model

        from volunteer.models import Team, VolunteerProfile

        source = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        lead = VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="lead"), conference=source
        )
        team = Team.objects.create(
            conference=source,
            short_name="Comms",
            description="Communications team",
            open_to_new_members=False,
        )
        team.team_leads.add(lead)

        created = target.clone_teams_from(source)

        assert created == 1
        cloned = target.teams.get()
        assert cloned.short_name == "Comms"
        assert cloned.description == "Communications team"
        assert cloned.open_to_new_members is False
        assert cloned.team_leads.count() == 0  # leads are per-edition

    def test_skips_teams_already_present(self):
        from volunteer.models import Team

        source = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        Team.objects.create(conference=source, short_name="Comms", description="a")
        Team.objects.create(conference=source, short_name="Design", description="b")
        Team.objects.create(
            conference=target, short_name="Comms", description="kept as-is"
        )

        created = target.clone_teams_from(source)

        assert created == 1  # only Design is new; Comms already exists
        assert set(target.teams.values_list("short_name", flat=True)) == {
            "Comms",
            "Design",
        }
        assert target.teams.get(short_name="Comms").description == "kept as-is"
