import pytest

from portal.context_processors import active_conference
from portal.models import Conference


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
