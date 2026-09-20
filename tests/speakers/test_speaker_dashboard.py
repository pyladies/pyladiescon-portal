import re
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from speakers.checklists import add_adhoc_item, block_item, complete_item, skip_item
from speakers.constants import (
    AutoRule,
    Delivery,
    ItemOwner,
    ItemStatus,
)
from speakers.models import ChecklistItem

from .factories import add_presenter, make_presenter, make_session, make_settings

DASHBOARD = reverse("speakers:my_dashboard")


def toggle(item):
    return reverse("speakers:my_item_toggle", args=[item.pk])


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, speaker):
    make_settings(conference)
    return make_presenter(
        conference,
        display_name="Ada",
        email="ada@example.com",
        user=speaker,
        timezone="Africa/Lagos",
    )


@pytest.fixture
def session(conference, presenter):
    session = make_session(conference, title="Django 101")
    add_presenter(session, presenter, confirmed=True)
    return session


@pytest.mark.django_db
class TestDashboardLists:
    def test_renders_with_zero_items(self, client, speaker, presenter, session):
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "Nothing on your list yet" in content
        assert "Dates are in Africa/Lagos" in content
        assert "Django 101" in content and "Not yet public" in content
        assert "to-dos done" not in content

    def test_two_lists_summary_and_assignee(
        self, client, speaker, presenter, session, conference
    ):
        lena = User.objects.create_user(
            username="lena", first_name="Lena", last_name="K"
        )
        mine = add_adhoc_item(
            conference,
            "Read the guide",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        done = add_adhoc_item(
            conference,
            "Register",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        complete_item(done)
        theirs = add_adhoc_item(
            conference,
            "Promo materials",
            ItemOwner.ORGANIZER,
            presenter=presenter,
            session=session,
            assignee=lena,
        )
        unassigned = add_adhoc_item(
            conference,
            "Schedule confirmation",
            ItemOwner.ORGANIZER,
            presenter=presenter,
        )
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "1 of 2 to-dos done" in content
        assert toggle(mine) in content and toggle(done) in content
        assert toggle(theirs) not in content and toggle(unassigned) not in content
        assert "Lena K" in content and "unassigned" in content
        assert re.search(r'data-item-id="%d"\s+data-status="DONE"' % done.pk, content)

    def test_automatic_item_is_dashed_and_not_tickable(
        self, client, speaker, presenter, session, conference
    ):
        auto = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Bio and headshot",
            presenter=presenter,
            session=session,
            auto_complete_rule=AutoRule.BIO_AND_HEADSHOT,
        )
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "checklist-item-auto" in content
        assert toggle(auto) not in content
        assert "Ticks itself" in content

    def test_blocked_item_and_video_items(self, client, speaker, presenter, conference):
        jam = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        add_presenter(jam, presenter, role="PERFORMER", confirmed=True)
        length = add_adhoc_item(
            conference, "Check video length", ItemOwner.ORGANIZER, session=jam
        )
        block_item(length, "Video is 2:05 over the 10-minute limit.")
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "What we're doing with your video" in content
        assert "Blocked" in content
        assert "2:05 over the 10-minute limit" in content

    def test_overdue_in_presenter_timezone(
        self, client, speaker, presenter, session, conference
    ):
        late = add_adhoc_item(
            conference,
            "Late thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=date.today() - timedelta(days=2),
        )
        soon = add_adhoc_item(
            conference,
            "Soon thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=date.today() + timedelta(days=30),
        )
        client.force_login(speaker)
        response = client.get(DASHBOARD)
        content = response.content.decode()
        assert "(overdue)" in content
        by_id = {i.pk: i for i in response.context["speaker_items"]}
        assert by_id[late.pk].overdue is True
        assert by_id[soon.pk].overdue is False


@pytest.mark.django_db
class TestToggle:
    def test_tick_and_untick_own_item(
        self, client, speaker, presenter, session, conference
    ):
        item = add_adhoc_item(
            conference, "Read the guide", ItemOwner.SPEAKER, presenter=presenter
        )
        client.force_login(speaker)
        assertRedirects(client.post(toggle(item)), DASHBOARD)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        assert item.completed_by == speaker
        client.post(toggle(item))
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO
        skip_item(item, note="not needed")
        response = client.post(toggle(item), follow=True)
        item.refresh_from_db()
        assert item.status == ItemStatus.SKIPPED
        assert "An organizer skipped" in response.content.decode()

    def test_cannot_tick_organizer_item(self, client, speaker, presenter, conference):
        item = add_adhoc_item(
            conference, "Promo", ItemOwner.ORGANIZER, presenter=presenter
        )
        client.force_login(speaker)
        assert client.post(toggle(item)).status_code == 403
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO

    def test_cannot_tick_another_presenters_item(
        self, client, speaker, presenter, conference
    ):
        other = make_presenter(conference)
        item = add_adhoc_item(conference, "Theirs", ItemOwner.SPEAKER, presenter=other)
        client.force_login(speaker)
        assert client.post(toggle(item)).status_code == 404

    def test_cannot_tick_automatic_item(self, client, speaker, presenter, conference):
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Registered",
            presenter=presenter,
            auto_complete_rule=AutoRule.PRETIX_REGISTERED,
        )
        client.force_login(speaker)
        response = client.post(toggle(item), follow=True)
        assert "completes itself" in response.content.decode()
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO

    def test_requires_presenter(self, client, portal_user, conference):
        make_settings(conference)
        item = add_adhoc_item(
            conference, "x", ItemOwner.SPEAKER, presenter=make_presenter(conference)
        )
        client.force_login(portal_user)
        assert client.post(toggle(item)).status_code == 403
