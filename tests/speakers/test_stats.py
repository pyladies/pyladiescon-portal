from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from portal.common import get_stats_cached_values
from speakers.checklists import add_adhoc_item, block_item, complete_item, skip_item
from speakers.constants import ItemOwner
from speakers.stats import (
    CACHE_KEY_TASKS,
    CACHE_KEY_TASKS_DONE,
    CACHE_KEY_TASKS_DONE_PERCENT,
    CACHE_KEY_TASKS_TOTAL,
    edition_task_stats,
    get_task_stats_dict,
    my_task_stats,
)
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

TODAY = date.today()


@pytest.fixture
def world(conference):
    """Ada with four to-dos (one done, one overdue, one skipped, one due soon)
    and three team items (one done by Vic, one for Vic's team, one nobody's)."""
    make_settings(conference)
    session = make_session(conference, title="Django 101")
    ada = make_presenter(conference, display_name="Ada")
    add_presenter(session, ada, confirmed=True)
    vic = User.objects.create_user(username="vic", email="vic@example.com")
    VolunteerProfile.objects.create(
        user=vic, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    team = Team.objects.create(conference=conference, short_name="Design")
    VolunteerProfile.objects.get(user=vic).teams.add(team)

    def item(title, owner=ItemOwner.SPEAKER, **kwargs):
        return add_adhoc_item(conference, title, owner, presenter=ada, **kwargs)

    complete_item(item("Bio"))
    item("Slides", due_date=TODAY - timedelta(days=1))
    skip_item(item("Not needed"))
    item("Register", due_date=TODAY + timedelta(days=3))
    done_by_vic = item("Promo card", ItemOwner.ORGANIZER, assignee=vic)
    complete_item(done_by_vic, actor=vic)
    blocked = item("Cut video", ItemOwner.ORGANIZER, team=team, due_date=TODAY)
    block_item(blocked, "Too long")
    item("Nobody's", ItemOwner.ORGANIZER)
    return {"ada": ada, "vic": vic, "team": team}


@pytest.mark.django_db
class TestEditionStats:
    def test_counts(self, conference, world):
        stats = edition_task_stats(conference, today=TODAY)
        assert stats["total"] == 6  # the skipped one is out of scope
        assert stats["done"] == 2 and stats["open"] == 4
        assert stats["done_percent"] == 33
        assert stats["overdue"] == 1 and stats["due_this_week"] == 2
        assert stats["blocked"] == 1 and stats["unassigned"] == 1
        assert (stats["speaker_done"], stats["speaker_total"]) == (1, 3)
        assert (stats["team_done"], stats["team_total"]) == (1, 3)
        assert stats["speaker_percent"] == 33 and stats["team_percent"] == 33

    def test_empty_edition(self, conference):
        stats = edition_task_stats(conference)
        assert stats["total"] == 0 and stats["done_percent"] == 0


@pytest.mark.django_db
class TestMyStats:
    def test_counts_mine_and_my_teams(self, conference, world):
        stats = my_task_stats(world["vic"], conference, today=TODAY)
        assert stats["total"] == 2 and stats["done"] == 1 and stats["open"] == 1
        assert stats["done_percent"] == 50
        assert stats["overdue"] == 0 and stats["due_this_week"] == 1
        assert stats["blocked"] == 1 and stats["done_by_me"] == 1

    def test_nothing_assigned(self, conference, world):
        stranger = User.objects.create_user(username="s")
        assert my_task_stats(stranger, conference)["total"] == 0


@pytest.mark.django_db
class TestPublicStats:
    def test_empty_when_module_off(self, conference):
        assert get_task_stats_dict(conference) == {}
        assert CACHE_KEY_TASKS_TOTAL not in get_stats_cached_values(conference)

    def test_totals_only_and_cached(self, conference, world):
        cache.delete(f"{CACHE_KEY_TASKS}_{conference.year}")
        values = get_task_stats_dict(conference)
        assert values == {
            CACHE_KEY_TASKS_TOTAL: 6,
            CACHE_KEY_TASKS_DONE: 2,
            CACHE_KEY_TASKS_DONE_PERCENT: 33,
        }
        complete_item(world["ada"].checklist_items.get(title="Register"))
        assert get_task_stats_dict(conference)[CACHE_KEY_TASKS_DONE] == 2  # cached
        cache.delete(f"{CACHE_KEY_TASKS}_{conference.year}")
        assert get_task_stats_dict(conference)[CACHE_KEY_TASKS_DONE] == 3
        assert get_stats_cached_values(conference)[CACHE_KEY_TASKS_TOTAL] == 6

    def test_stats_page_and_json(self, client, conference, world):
        cache.delete(f"{CACHE_KEY_TASKS}_{conference.year}")
        content = client.get(reverse("portal_stats")).content.decode()
        assert "Conference Tasks" in content and "Tasks Completed" in content
        assert "speaker" not in content.split("Conference Tasks")[1][:600].lower()
        data = client.get(reverse("portal_stats_json")).json()["stats"]
        assert data[CACHE_KEY_TASKS_TOTAL] == 6 and data[CACHE_KEY_TASKS_DONE] == 2


@pytest.mark.django_db
class TestDashboards:
    def test_volunteer_hub_shows_my_numbers(self, client, conference, world):
        client.force_login(world["vic"])
        response = client.get(reverse("volunteer:index"))
        content = response.content.decode()
        assert "My volunteering tasks" in content
        assert response.context["task_stats"]["total"] == 2
        assert "1 of 2 tasks" in content and "50%" in content
        assert reverse("speakers:checklist_queue") in content
        assert "Nothing assigned to you yet" not in content

    def test_volunteer_hub_hides_numbers_without_access(
        self, client, conference, world
    ):
        outsider = User.objects.create_user(username="out")
        client.force_login(outsider)
        response = client.get(reverse("volunteer:index"))
        assert response.context["task_stats"] is None
        assert "My volunteering tasks" not in response.content.decode()

    def test_organizer_sees_the_hub_section_even_when_empty(self, client, conference):
        make_settings(conference)
        organizer = User.objects.create_user(username="org", is_staff=True)
        client.force_login(organizer)
        content = client.get(reverse("volunteer:index")).content.decode()
        assert "My volunteering tasks" in content
        assert "Nothing assigned to you yet" in content

    def test_organizer_dashboard_edition_numbers(self, client, conference, world):
        organizer = User.objects.create_user(username="org", is_staff=True)
        client.force_login(organizer)
        response = client.get(reverse("organizer_dashboard"))
        content = response.content.decode()
        assert "Conference tasks" in content
        assert response.context["task_stats"]["unassigned"] == 1
        assert "Speakers: 1 of 3 done (33%). Team: 1 of 3 done (33%)." in content
        assert reverse("speakers:checklist_board") in content

    def test_organizer_dashboard_without_module(self, client, conference):
        organizer = User.objects.create_user(username="org", is_staff=True)
        client.force_login(organizer)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["task_stats"] is None
        assert "Conference tasks" not in response.content.decode()
