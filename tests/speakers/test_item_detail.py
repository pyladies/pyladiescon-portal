from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from speakers.checklists import (
    add_adhoc_item,
    assign_item,
    block_item,
    complete_item,
    skip_item,
)
from speakers.constants import ItemOwner
from speakers.models import Handbook
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

TODAY = date.today()


def detail(item):
    return reverse("speakers:item_detail", args=[item.pk])


def my_detail(item):
    return reverse("speakers:my_item_detail", args=[item.pk])


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="org", email="org@example.com", is_staff=True
    )


@pytest.fixture
def liaison(db, conference):
    user = User.objects.create_user(username="lena", email="lena@example.com")
    VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    return user


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def world(conference, enabled, liaison, speaker):
    """Ada (liaised by Lena) on a workshop; Grace on her own talk."""
    session = make_session(conference, title="Django 101")
    ada = make_presenter(
        conference,
        display_name="Ada",
        email="ada@example.com",
        user=speaker,
        liaison=liaison,
    )
    add_presenter(session, ada, confirmed=True)
    other_session = make_session(conference, title="Typing")
    grace = make_presenter(conference, display_name="Grace")
    add_presenter(other_session, grace, confirmed=True)
    todo = add_adhoc_item(
        conference,
        "Send your slides",
        ItemOwner.SPEAKER,
        presenter=ada,
        session=session,
        due_date=TODAY - timedelta(days=2),
        description_md="Upload them **as PDF** please.",
    )
    team_item = add_adhoc_item(
        conference,
        "Promo card",
        ItemOwner.ORGANIZER,
        presenter=ada,
        session=session,
        assignee=liaison,
    )
    video_item = add_adhoc_item(
        conference, "Add title card", ItemOwner.ORGANIZER, session=session
    )
    graces = add_adhoc_item(
        conference, "Grace's thing", ItemOwner.SPEAKER, presenter=grace
    )
    return {
        "session": session,
        "ada": ada,
        "grace": grace,
        "todo": todo,
        "team_item": team_item,
        "video_item": video_item,
        "graces": graces,
    }


@pytest.mark.django_db
class TestSpeakerItemDetail:
    def test_own_item_in_full(self, client, speaker, world):
        client.force_login(speaker)
        response = client.get(my_detail(world["todo"]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Send your slides" in content
        assert "<strong>as PDF</strong>" in content
        assert "overdue" in content and "Django 101" in content
        assert reverse("speakers:my_item_toggle", args=[world["todo"].pk]) in content
        assert "Mark as done" in content

    def test_toggle_returns_to_the_detail_page(self, client, speaker, world):
        client.force_login(speaker)
        response = client.post(
            reverse("speakers:my_item_toggle", args=[world["todo"].pk]),
            {"next": my_detail(world["todo"])},
        )
        assertRedirects(response, f"{my_detail(world['todo'])}#item-{world['todo'].pk}")
        content = client.get(my_detail(world["todo"])).content.decode()
        assert "Mark as not done" in content and "by ada" in content

    def test_team_item_shows_who_is_on_it_and_who_completed(
        self, client, speaker, world, liaison
    ):
        client.force_login(speaker)
        content = client.get(my_detail(world["team_item"])).content.decode()
        assert "The team handles this one" in content and "lena" in content
        assert "Mark as done" not in content
        complete_item(world["team_item"], actor=liaison)
        content = client.get(my_detail(world["team_item"])).content.decode()
        assert "by lena" in content

    def test_session_level_item_on_my_session(self, client, speaker, world):
        client.force_login(speaker)
        response = client.get(my_detail(world["video_item"]))
        assert response.status_code == 200
        assert "Add title card" in response.content.decode()

    def test_someone_elses_item_is_404(self, client, speaker, world, conference):
        client.force_login(speaker)
        assert client.get(my_detail(world["graces"])).status_code == 404
        elsewhere = add_adhoc_item(
            conference,
            "Not yours",
            ItemOwner.ORGANIZER,
            session=make_session(conference),
        )
        assert client.get(my_detail(elsewhere)).status_code == 404

    def test_guide_link_blocked_note_and_general_item(
        self, client, speaker, world, conference
    ):
        Handbook.objects.create(
            conference=conference, key="speaker", title="Speaker guide", url="https://x"
        ).publish()
        guide_item = add_adhoc_item(
            conference, "Read the guide", ItemOwner.SPEAKER, presenter=world["ada"]
        )
        guide_item.requires_handbook = "speaker"
        guide_item.auto_complete_rule = "handbook_read"
        guide_item.save()
        block_item(world["todo"], "Video is too long")
        client.force_login(speaker)
        content = client.get(my_detail(guide_item)).content.decode()
        assert "Read the Speaker guide" in content
        assert "ticks itself" in content and "General, not tied" in content
        content = client.get(my_detail(world["todo"])).content.decode()
        assert "Video is too long" in content and "Blocked" in content

    def test_only_a_blocked_note_reaches_the_presenter(
        self, client, speaker, world, liaison
    ):
        """A note written on a skip or a completion is internal.

        The checklist list has always shown a note only on a blocked item;
        the item page follows the same rule, or an organizer's "she never
        answered three emails" lands in front of the speaker.
        """
        team_item = world["team_item"]
        skip_item(team_item, actor=liaison, note="Not worth chasing her again")
        client.force_login(speaker)
        content = client.get(my_detail(team_item)).content.decode()
        assert "Not worth chasing" not in content
        complete_item(world["todo"], actor=liaison, note="chased her for weeks")
        content = client.get(my_detail(world["todo"])).content.decode()
        assert "chased her for weeks" not in content
        # The organizing side still reads every note.
        client.force_login(liaison)
        assert "Not worth chasing" in client.get(detail(team_item)).content.decode()

    def test_list_links_to_the_detail_page(self, client, speaker, world):
        client.force_login(speaker)
        content = client.get(reverse("speakers:my_checklist")).content.decode()
        assert my_detail(world["todo"]) in content


@pytest.mark.django_db
class TestOrganizerItemDetail:
    def test_organizer_gets_actions_history_and_links(
        self, client, organizer, world, liaison
    ):
        item = world["team_item"]
        client.force_login(organizer)
        response = client.get(detail(item))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Promo card" in content
        assert world["ada"].get_absolute_url() in content
        assert world["session"].get_absolute_url() in content
        assert reverse("speakers:item_assign", args=[item.pk]) in content
        assert "Mark as done" in content and "Skip" in content
        assert "Organize" in content
        assert reverse("speakers:checklist_board") in content
        assert "History" in content
        assign_item(item, assignee=organizer, actor=organizer)
        content = client.get(detail(item)).content.decode()
        assert "Promo card → org" in content

    def test_status_and_assign_return_to_detail(self, client, organizer, world):
        item = world["team_item"]
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]),
            {"status": "SKIPPED", "note": "Not needed", "next": detail(item)},
        )
        assertRedirects(response, detail(item))
        content = client.get(detail(item)).content.decode()
        assert "Not needed" in content and "Reopen" in content
        assert 'value="SKIPPED"' not in content
        response = client.post(
            reverse("speakers:item_assign", args=[item.pk]),
            {"owner": f"user:{organizer.pk}", "next": detail(item)},
        )
        assertRedirects(response, detail(item))

    def test_automatic_item_has_no_status_buttons(self, client, organizer, world):
        item = world["todo"]
        item.auto_complete_rule = "bio_and_headshot"
        item.save()
        client.force_login(organizer)
        content = client.get(detail(item)).content.decode()
        assert "ticks itself" in content and "Mark as done" not in content

    def test_liaison_scope(self, client, liaison, world):
        client.force_login(liaison)
        assert client.get(detail(world["team_item"])).status_code == 200
        assert client.get(detail(world["graces"])).status_code == 403

    def test_volunteer_gets_personal_shell_without_assign(
        self, client, world, conference
    ):
        vic = User.objects.create_user(username="vic", email="vic@example.com")
        VolunteerProfile.objects.create(
            user=vic,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        team = Team.objects.create(conference=conference, short_name="Design")
        VolunteerProfile.objects.get(user=vic).teams.add(team)
        assign_item(world["video_item"], team=team)
        client.force_login(vic)
        response = client.get(detail(world["video_item"]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "My volunteering" in content and "My volunteering tasks" in content
        assert (
            reverse("speakers:item_assign", args=[world["video_item"].pk])
            not in content
        )
        assert world["session"].get_absolute_url() not in content
        assert "Django 101" in content
        assert "Mark as done" in content
        # Skipping is the organizing side's call, in the page and in the view.
        assert "Skip" not in content
        refused = client.post(
            reverse("speakers:item_status", args=[world["video_item"].pk]),
            {"status": "SKIPPED", "note": "internal: not worth chasing"},
        )
        assert refused.status_code == 403
        world["video_item"].refresh_from_db()
        assert world["video_item"].note == ""
        assert client.get(detail(world["team_item"])).status_code == 403

    def test_queue_and_presenter_page_link_to_detail(
        self, client, organizer, liaison, world
    ):
        client.force_login(liaison)
        content = client.get(reverse("speakers:checklist_queue")).content.decode()
        assert detail(world["team_item"]) in content
        client.force_login(organizer)
        content = client.get(world["ada"].get_absolute_url()).content.decode()
        assert detail(world["team_item"]) in content

    def test_other_edition_item_404(self, client, organizer, enabled, world):
        assert client.get(detail(world["todo"])).status_code == 302
        client.force_login(organizer)
        assert (
            client.get(
                detail(world["todo"]).replace(str(world["todo"].pk), "999999")
            ).status_code
            == 404
        )
