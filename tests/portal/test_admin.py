import pytest
from django.urls import reverse

from portal.models import Conference


@pytest.fixture(autouse=True)
def conference():
    """This module creates its own Conference rows, so skip the shared one."""
    return None


@pytest.mark.django_db
class TestCloneTeamsAction:
    def _run_action(self, client, pks):
        return client.post(
            reverse("admin:portal_conference_changelist"),
            {"action": "clone_teams_from_previous", "_selected_action": pks},
            follow=True,
        )

    def test_clones_teams_from_previous_edition(self, client, admin_user):
        from volunteer.models import Team

        source = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        Team.objects.create(conference=source, short_name="Comms", description="c")
        client.force_login(admin_user)

        response = self._run_action(client, [target.pk])

        assert response.status_code == 200
        assert target.teams.count() == 1
        assert "Cloned 1 team(s)" in response.content.decode()

    def test_warns_when_no_previous_edition(self, client, admin_user):
        target = Conference.objects.create(
            year=2026, name="PyLadiesCon 2026", slug="2026"
        )
        client.force_login(admin_user)

        response = self._run_action(client, [target.pk])

        assert response.status_code == 200
        assert target.teams.count() == 0
        assert "No previous edition" in response.content.decode()
