import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from portal.models import Conference
from portal.services import (
    bring_forward_volunteers,
    clone_sponsorship_tiers,
    clone_teams,
    freeze_stats,
)
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


@pytest.fixture(autouse=True)
def conference():
    """These tests create their own Conference rows, so skip the shared one."""
    return None


@pytest.mark.django_db
class TestCloneTeams:
    def test_copies_team_structure_but_not_leads(self):
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

        created = clone_teams(target, source)

        assert created == 1
        cloned = target.teams.get()
        assert cloned.short_name == "Comms"
        assert cloned.description == "Communications team"
        assert cloned.open_to_new_members is False
        assert cloned.team_leads.count() == 0  # leads are per-edition

    def test_skips_teams_already_present(self):
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

        created = clone_teams(target, source)

        assert created == 1  # only Design is new; Comms already exists
        assert set(target.teams.values_list("short_name", flat=True)) == {
            "Comms",
            "Design",
        }
        assert target.teams.get(short_name="Comms").description == "kept as-is"


@pytest.mark.django_db
class TestCloneSponsorshipTiers:
    def test_copies_tiers_skipping_existing(self):
        source = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        SponsorshipTier.objects.create(
            conference=source, name="Gold", amount=1000, description="g"
        )
        SponsorshipTier.objects.create(
            conference=source, name="Silver", amount=500, description="s"
        )
        SponsorshipTier.objects.create(
            conference=target, name="Gold", amount=999, description="kept"
        )

        created = clone_sponsorship_tiers(target, source)

        assert created == 1  # only Silver; Gold already exists
        assert set(target.sponsorship_tiers.values_list("name", flat=True)) == {
            "Gold",
            "Silver",
        }
        assert target.sponsorship_tiers.get(name="Gold").amount == 999


@pytest.mark.django_db
class TestBringForwardVolunteers:
    def test_brings_only_approved_as_pending(self):
        source = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        user_model = get_user_model()
        approved_user = user_model.objects.create(username="appr")
        pending_user = user_model.objects.create(username="pend")
        VolunteerProfile.objects.create(
            user=approved_user,
            conference=source,
            application_status=ApplicationStatus.APPROVED,
        )
        VolunteerProfile.objects.create(
            user=pending_user,
            conference=source,
            application_status=ApplicationStatus.PENDING,
        )

        created = bring_forward_volunteers(target, source)

        assert created == 1  # only the approved volunteer
        new = VolunteerProfile.objects.get(user=approved_user, conference=target)
        assert new.application_status == ApplicationStatus.PENDING
        assert not VolunteerProfile.objects.filter(
            user=pending_user, conference=target
        ).exists()


@pytest.mark.django_db
class TestFreezeStats:
    def test_snapshots_live_metrics_as_json_safe(self):
        cache.clear()
        conf = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        SponsorshipProfile.objects.create(
            organization_name="Acme",
            conference=conf,
            progress_status=SponsorshipProgressStatus.PAID,
            sponsorship_override_amount=5000,
        )

        snapshot = freeze_stats(conf)

        assert snapshot["sponsors"] == 1
        assert snapshot["sponsorship_amount"] == 5000.0
        assert isinstance(snapshot["sponsorship_amount"], float)  # JSON-safe
        assert isinstance(snapshot["donation_amount"], float)
        assert snapshot["registrations"] == 0
        assert snapshot["donors"] == 0

        conf.refresh_from_db()
        assert conf.historical_snapshot == snapshot
