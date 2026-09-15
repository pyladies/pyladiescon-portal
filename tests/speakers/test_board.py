from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.board import build_board, cell_class
from speakers.checklists import add_adhoc_item, block_item, complete_item, skip_item
from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.models import ActivityLog, ChecklistItem
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

BOARD = reverse("speakers:checklist_board")
QUEUE = reverse("speakers:checklist_queue")
EXPORT = reverse("speakers:checklist_board_export")
TODAY = date.today()


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True, first_name="Org"
    )


@pytest.fixture
def liaison(db, conference):
    user = User.objects.create_user(
        username="lena", email="lena@example.com", first_name="Lena"
    )
    VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    return user


@pytest.fixture
def people(conference, enabled, liaison):
    """Ada (liaised by Lena, one overdue), Grace (all done), Mary (nothing)."""
    session = make_session(conference, title="Django 101")
    ada = make_presenter(conference, display_name="Ada", liaison=liaison)
    grace = make_presenter(conference, display_name="Grace")
    mary = make_presenter(conference, display_name="Mary")
    add_presenter(session, ada, confirmed=True)
    add_presenter(session, grace, confirmed=True)
    items = {}
    for presenter in (ada, grace):
        items[presenter.display_name, "bio"] = add_adhoc_item(
            conference,
            "Update bio",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
            due_date=TODAY - timedelta(days=3),
        )
        items[presenter.display_name, "register"] = add_adhoc_item(
            conference,
            "Register",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=TODAY + timedelta(days=10),
        )
        items[presenter.display_name, "promo"] = add_adhoc_item(
            conference,
            "Promo materials",
            ItemOwner.ORGANIZER,
            presenter=presenter,
            due_date=TODAY + timedelta(days=5),
            assignee=liaison,
        )
    complete_item(items["Grace", "bio"])
    complete_item(items["Grace", "register"])
    return {
        "session": session,
        "ada": ada,
        "grace": grace,
        "mary": mary,
        "items": items,
    }


@pytest.mark.django_db
class TestBoard:
    def test_access(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(BOARD).status_code == 403

    def test_speaker_tab_sorted_by_most_overdue(self, client, organizer, people):
        client.force_login(organizer)
        response = client.get(BOARD)
        board = response.context["board"]
        assert board["columns"] == ["Update bio", "Register"]
        names = [row["presenter"].display_name for row in board["rows"]]
        assert names == ["Ada", "Grace", "Mary"]
        ada = board["rows"][0]
        assert ada["overdue"] == 1 and ada["open"] == 2
        assert ada["next_due"] == TODAY - timedelta(days=3)
        assert [css for _, css in ada["cells"]] == ["cell-overdue", "cell-todo"]
        grace = board["rows"][1]
        assert [css for _, css in grace["cells"]] == ["cell-done", "cell-done"]
        mary = board["rows"][2]
        assert [css for _, css in mary["cells"]] == ["cell-none", "cell-none"]
        content = response.content.decode()
        assert "Lena" in content and "Speaker side" in content

    def test_organizer_tab_and_name_sort(self, client, organizer, people):
        client.force_login(organizer)
        board = client.get(BOARD, {"tab": "organizer", "sort": "name"}).context["board"]
        assert board["columns"] == ["Promo materials"]
        assert [r["presenter"].display_name for r in board["rows"]] == [
            "Ada",
            "Grace",
            "Mary",
        ]

    def test_unknown_tab_falls_back(self, client, organizer, people):
        client.force_login(organizer)
        assert client.get(BOARD, {"tab": "nope"}).context["tab"] == ItemOwner.SPEAKER

    def test_liaison_sees_only_own_presenters(self, client, liaison, people):
        client.force_login(liaison)
        board = client.get(BOARD).context["board"]
        assert [r["presenter"].display_name for r in board["rows"]] == ["Ada"]

    @pytest.mark.parametrize("tab", ["speaker", "organizer"])
    def test_query_count_constant_per_tab(
        self, client, organizer, people, conference, tab
    ):
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(BOARD, {"tab": tab})
        for n in range(5):
            presenter = make_presenter(conference, liaison=organizer)
            for title in ("Update bio", "Register", "Extra"):
                add_adhoc_item(
                    conference, title, ItemOwner.SPEAKER, presenter=presenter
                )
                add_adhoc_item(
                    conference, title, ItemOwner.ORGANIZER, presenter=presenter
                )
        with CaptureQueriesContext(connection) as after:
            client.get(BOARD, {"tab": tab})
        assert len(after) == len(before)

    def test_same_title_on_two_sessions_keeps_most_urgent(
        self, organizer, people, conference
    ):
        ada = people["ada"]
        other = make_session(conference, title="Panel")
        add_presenter(other, ada, confirmed=True)
        done = add_adhoc_item(
            conference, "Update bio", ItemOwner.SPEAKER, presenter=ada, session=other
        )
        complete_item(done)
        board = build_board(conference, organizer, ItemOwner.SPEAKER)
        row = next(r for r in board["rows"] if r["presenter"] == ada)
        cell, css = row["cells"][0]
        assert cell == people["items"]["Ada", "bio"] and css == "cell-overdue"
        # A blocked item outranks a plain to-do without a date.
        blocked = add_adhoc_item(
            conference, "Register", ItemOwner.SPEAKER, presenter=ada, session=other
        )
        block_item(blocked, "nope")
        board = build_board(conference, organizer, ItemOwner.SPEAKER)
        row = next(r for r in board["rows"] if r["presenter"] == ada)
        assert row["cells"][1][1] == "cell-todo"  # dated to-do stays ahead of the block
        assert cell_class(blocked, TODAY) == "cell-blocked"
        skip_item(blocked)
        assert cell_class(blocked, TODAY) == "cell-skipped"

    def test_empty_board(self, client, organizer, enabled):
        client.force_login(organizer)
        assert "No presenters with checklists yet" in client.get(BOARD).content.decode()

    def test_rail_links(self, client, organizer, enabled):
        client.force_login(organizer)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert BOARD in content and QUEUE in content

    def test_csv_export(self, client, organizer, people):
        client.force_login(organizer)
        response = client.get(EXPORT, {"tab": "speaker"})
        assert response["Content-Type"] == "text/csv"
        assert (
            'filename="checklists-speaker-2025.csv"' in response["Content-Disposition"]
        )
        lines = response.content.decode().splitlines()
        assert lines[0] == "Presenter,Email,Liaison,Overdue,Update bio,Register"
        assert lines[1].startswith("Ada,presenter") and lines[1].endswith(
            ",Lena,1,To do,To do"
        )
        assert lines[2].endswith(",,0,Done,Done")
        assert lines[3].endswith(",,0,,")


@pytest.mark.django_db
class TestQueue:
    def test_lists_my_open_items_soonest_first(
        self, client, liaison, people, conference
    ):
        ada = people["ada"]
        later = add_adhoc_item(
            conference,
            "Later",
            ItemOwner.ORGANIZER,
            presenter=ada,
            due_date=TODAY + timedelta(days=30),
            assignee=liaison,
        )
        undated = add_adhoc_item(
            conference, "Undated", ItemOwner.ORGANIZER, presenter=ada, assignee=liaison
        )
        done = add_adhoc_item(
            conference,
            "Done already",
            ItemOwner.ORGANIZER,
            presenter=ada,
            assignee=liaison,
        )
        complete_item(done)
        add_adhoc_item(conference, "Someone else's", ItemOwner.ORGANIZER, presenter=ada)
        client.force_login(liaison)
        response = client.get(QUEUE)
        titles = [i.title for i in response.context["items"]]
        assert titles == ["Promo materials", "Promo materials", "Later", "Undated"]
        assert later in response.context["items"]
        assert undated in response.context["items"]
        assert "Ada" in response.content.decode()

    def test_empty_queue(self, client, organizer, enabled):
        client.force_login(organizer)
        assert "Nothing assigned to you" in client.get(QUEUE).content.decode()

    def test_complete_from_queue_returns_to_queue(self, client, liaison, people):
        item = people["items"]["Ada", "promo"]
        client.force_login(liaison)
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]),
            {"status": "DONE", "next": QUEUE},
        )
        assertRedirects(response, QUEUE)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE and item.completed_by == liaison


@pytest.mark.django_db
class TestPresenterPageChecklists:
    def test_both_lists_and_forms(self, client, organizer, people):
        ada = people["ada"]
        client.force_login(organizer)
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "Their to-dos" in content and "What we're doing for them" in content
        assert "Update bio" in content and "Promo materials" in content
        assert (
            reverse("speakers:item_assign", args=[people["items"]["Ada", "promo"].pk])
            in content
        )
        assert reverse("speakers:presenter_add_item", args=[ada.pk]) in content
        assert 'name="assignee"' in content and "Lena" in content
        assert "htmx.min.js" in content

    def test_add_one_off_item(self, client, organizer, people, liaison):
        ada = people["ada"]
        client.force_login(organizer)
        url = reverse("speakers:presenter_add_item", args=[ada.pk])
        response = client.post(
            url,
            {
                "title": "Send swag",
                "owner": ItemOwner.ORGANIZER,
                "due_date": "2026-11-01",
                "assignee": liaison.pk,
                "description_md": "T-shirt size M",
            },
        )
        assertRedirects(response, ada.get_absolute_url())
        item = ada.checklist_items.get(title="Send swag")
        assert item.assignee == liaison and item.due_date == date(2026, 11, 1)
        assert item.description_md == "T-shirt size M"
        response = client.post(
            url, {"title": "", "owner": ItemOwner.SPEAKER}, follow=True
        )
        assert "give it a title" in response.content.decode()

    def test_liaison_can_add_for_own_presenter_only(self, client, liaison, people):
        client.force_login(liaison)
        ok = reverse("speakers:presenter_add_item", args=[people["ada"].pk])
        assert (
            client.post(ok, {"title": "x", "owner": ItemOwner.SPEAKER}).status_code
            == 302
        )
        other = reverse("speakers:presenter_add_item", args=[people["grace"].pk])
        assert (
            client.post(other, {"title": "x", "owner": ItemOwner.SPEAKER}).status_code
            == 404
        )


@pytest.mark.django_db
class TestItemActions:
    def test_assign_logged_and_htmx_row(self, client, organizer, people, liaison):
        item = people["items"]["Grace", "promo"]
        client.force_login(organizer)
        url = reverse("speakers:item_assign", args=[item.pk])
        response = client.post(url, {"assignee": ""}, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        html = response.content.decode()
        assert html.lstrip().startswith("<tr") and f'id="item-{item.pk}"' in html
        item.refresh_from_db()
        assert item.assignee is None
        entry = ActivityLog.objects.get(action="checklist.assigned")
        assert entry.actor == organizer and "→ nobody" in entry.message
        response = client.post(url, {"assignee": liaison.pk})
        assertRedirects(response, people["grace"].get_absolute_url())
        item.refresh_from_db()
        assert item.assignee == liaison
        assert client.post(url, {"assignee": 999999}).status_code == 400

    def test_status_changes(self, client, organizer, people):
        item = people["items"]["Ada", "register"]
        client.force_login(organizer)
        url = reverse("speakers:item_status", args=[item.pk])
        client.post(url, {"status": "DONE"})
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        client.post(url, {"status": "TODO"})
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO
        client.post(url, {"status": "SKIPPED", "note": "not needed"})
        item.refresh_from_db()
        assert item.status == ItemStatus.SKIPPED and item.note == "not needed"
        assert client.post(url, {"status": "BOGUS"}).status_code == 400

    def test_automatic_item_status_refused_with_message(
        self, client, organizer, people, conference
    ):
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="auto",
            presenter=people["ada"],
            auto_complete_rule=AutoRule.HANDBOOK_READ,
        )
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]),
            {"status": "DONE"},
            follow=True,
        )
        assert "completes itself" in response.content.decode()

    def test_liaison_scope(self, client, liaison, people, conference):
        mine = people["items"]["Ada", "promo"]
        theirs = people["items"]["Grace", "promo"]
        session_item = add_adhoc_item(
            conference, "Session-level", ItemOwner.ORGANIZER, session=people["session"]
        )
        client.force_login(liaison)
        assert (
            client.post(
                reverse("speakers:item_status", args=[mine.pk]), {"status": "DONE"}
            ).status_code
            == 302
        )
        assert (
            client.post(
                reverse("speakers:item_status", args=[theirs.pk]), {"status": "DONE"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                reverse("speakers:item_status", args=[session_item.pk]),
                {"status": "DONE"},
            ).status_code
            == 403
        )

    def test_session_item_redirects_to_session(
        self, client, organizer, people, conference
    ):
        item = add_adhoc_item(
            conference, "Session-level", ItemOwner.ORGANIZER, session=people["session"]
        )
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]), {"status": "DONE"}
        )
        assertRedirects(response, people["session"].get_absolute_url())
        response = client.post(
            reverse("speakers:item_assign", args=[item.pk]),
            {"assignee": ""},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_other_edition_item_404(self, client, organizer, enabled):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        item = add_adhoc_item(
            other, "x", ItemOwner.SPEAKER, presenter=make_presenter(other)
        )
        client.force_login(organizer)
        assert (
            client.post(
                reverse("speakers:item_status", args=[item.pk]), {"status": "DONE"}
            ).status_code
            == 404
        )
