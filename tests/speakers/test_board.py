from datetime import date, timedelta

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.board import build_board, cell_class
from speakers.checklists import (
    add_adhoc_item,
    assign_item,
    block_item,
    complete_item,
    skip_item,
)
from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.models import ActivityLog, ChecklistItem
from speakers.permissions import approved_teams, is_speaker_assignee
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

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
def design_team(conference, liaison):
    """A team with Lena (approved) and Mia (pending, so not a recipient)."""
    team = Team.objects.create(
        conference=conference, short_name="Design", description="d"
    )
    VolunteerProfile.objects.get(user=liaison).teams.add(team)
    mia = User.objects.create_user(username="mia", email="mia@example.com")
    VolunteerProfile.objects.create(user=mia, conference=conference).teams.add(team)
    return team


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
        assert lines[0].startswith('"One column per item title.')
        assert lines[1] == "Presenter,Email,Liaison,Overdue,Update bio,Register"
        assert lines[2].startswith("Ada,presenter") and lines[2].endswith(
            ",Lena,1,To do,To do"
        )
        assert lines[3].endswith(",,0,Done,Done")
        assert lines[4].endswith(",,0,,")

    def test_csv_never_exports_a_formula(self, client, organizer, people, conference):
        """A presenter types their own display name; a spreadsheet must show
        it, not run it."""
        evil = make_presenter(conference, display_name='=HYPERLINK("http://x","y")')
        add_adhoc_item(conference, "-Update bio", ItemOwner.SPEAKER, presenter=evil)
        client.force_login(organizer)
        text = client.get(EXPORT, {"tab": "speaker"}).content.decode()
        assert "'=HYPERLINK" in text and "\n=HYPERLINK" not in text
        assert "'-Update bio" in text


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
        assert reverse("speakers:presenter_add_item", args=[ada.slug]) in content
        assert 'name="owner"' in content and "Lena" in content
        assert '<optgroup label="Teams">' in content
        assert "htmx.min.js" in content

    def test_presenter_page_shows_item_descriptions(self, client, organizer, people):
        add_adhoc_item(
            people["ada"].conference,
            "Bring snacks",
            ItemOwner.SPEAKER,
            presenter=people["ada"],
            description_md="Something *salty*.",
        )
        client.force_login(organizer)
        page = client.get(people["ada"].get_absolute_url()).content.decode()
        assert "<em>salty</em>" in page

    def test_organizer_rows_credit_the_completer(
        self, client, organizer, people, liaison
    ):
        item = people["items"]["Ada", "promo"]
        complete_item(item, actor=liaison)
        client.force_login(organizer)
        content = client.get(people["ada"].get_absolute_url()).content.decode()
        assert "by Lena," in content

    def test_add_one_off_item(self, client, organizer, people, liaison):
        ada = people["ada"]
        client.force_login(organizer)
        url = reverse("speakers:presenter_add_item", args=[ada.slug])
        response = client.post(
            url,
            {
                "title": "Send swag",
                "owner_kind": ItemOwner.ORGANIZER,
                "due_date": "2026-11-01",
                "owner": f"user:{liaison.pk}",
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
        ok = reverse("speakers:presenter_add_item", args=[people["ada"].slug])
        assert (
            client.post(ok, {"title": "x", "owner": ItemOwner.SPEAKER}).status_code
            == 302
        )
        other = reverse("speakers:presenter_add_item", args=[people["grace"].slug])
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
        response = client.post(url, {"owner": ""}, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        html = response.content.decode()
        assert html.lstrip().startswith("<tr") and f'id="item-{item.pk}"' in html
        item.refresh_from_db()
        assert item.assignee is None
        entry = ActivityLog.objects.get(action="checklist.assigned")
        assert entry.actor == organizer and "→ nobody" in entry.message
        response = client.post(url, {"owner": f"user:{liaison.pk}"})
        assertRedirects(response, people["grace"].get_absolute_url())
        item.refresh_from_db()
        assert item.assignee == liaison
        assert client.post(url, {"owner": "user:999999"}).status_code == 400
        assert client.post(url, {"owner": "team:999999"}).status_code == 400

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
        """A liaison acts on their own presenters' items, and on anything
        handed to them; everything else is refused."""
        mine = people["items"]["Ada", "promo"]
        # Grace is not Lena's presenter, and this one is nobody's to carry.
        theirs = add_adhoc_item(
            conference,
            "Grace only",
            ItemOwner.ORGANIZER,
            presenter=people["grace"],
        )
        # Assigned to Lena though the presenter is not hers: hers to tick.
        assigned = people["items"]["Grace", "promo"]
        # Ada's own to-do, assigned to nobody: hers because Ada is hers.
        by_presenter = people["items"]["Ada", "bio"]
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
                reverse("speakers:item_status", args=[assigned.pk]), {"status": "DONE"}
            ).status_code
            == 302
        )
        assert (
            client.post(
                reverse("speakers:item_status", args=[by_presenter.pk]),
                {"status": "DONE"},
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
            {"owner": ""},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_next_only_returns_to_this_site(self, client, organizer, people):
        item = people["items"]["Ada", "register"]
        client.force_login(organizer)
        url = reverse("speakers:item_status", args=[item.pk])
        response = client.post(url, {"status": "DONE", "next": "https://evil.example/"})
        assertRedirects(response, people["ada"].get_absolute_url())
        response = client.post(url, {"status": "TODO", "next": QUEUE})
        assertRedirects(response, QUEUE)

    def test_liaison_cannot_reassign(self, client, liaison, people):
        """Liaisons tick and skip their presenter's items; handing organizer
        work to someone else is an organizer's call."""
        item = people["items"]["Ada", "promo"]
        client.force_login(liaison)
        response = client.post(
            reverse("speakers:item_assign", args=[item.pk]), {"assignee": ""}
        )
        assert response.status_code == 403
        page = client.get(people["ada"].get_absolute_url()).content.decode()
        # No inline reassign control on the row; the one-off item form (which
        # a liaison may use) keeps its own assignee field.
        assert reverse("speakers:item_assign", args=[item.pk]) not in page
        assert "Lena" in page

    def test_htmx_errors_show_in_the_row(self, client, organizer, people, conference):
        """A swapped row never displays queued messages, so the error rides
        along inside it; a 400 would be ignored by htmx."""
        auto = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="auto",
            presenter=people["ada"],
            auto_complete_rule=AutoRule.HANDBOOK_READ,
        )
        client.force_login(organizer)
        url = reverse("speakers:item_status", args=[auto.pk])
        html = client.post(
            url, {"status": "DONE"}, HTTP_HX_REQUEST="true"
        ).content.decode()
        assert html.lstrip().startswith("<tr") and "completes itself" in html
        html = client.post(
            url, {"status": "BOGUS"}, HTTP_HX_REQUEST="true"
        ).content.decode()
        assert "Unknown status." in html
        assert client.post(url, {"status": "BOGUS"}).status_code == 400

    def test_presenter_page_query_count_constant(self, client, organizer, people):
        """The assignee choices are one query for the page, not one per row."""
        client.force_login(organizer)
        url = people["ada"].get_absolute_url()
        with CaptureQueriesContext(connection) as before:
            client.get(url)
        for n in range(10):
            add_adhoc_item(
                people["ada"].conference,
                f"Task {n}",
                ItemOwner.ORGANIZER,
                presenter=people["ada"],
            )
        with CaptureQueriesContext(connection) as after:
            client.get(url)
        assert len(after) == len(before)

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


@pytest.fixture
def volunteer(db, conference):
    """An approved volunteer who neither organizes nor liaises."""
    user = User.objects.create_user(
        username="vera", email="vera@example.com", first_name="Vera"
    )
    VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    return user


@pytest.mark.django_db
class TestVolunteerAssignee:
    """A volunteer handed an organizer item can act on it (review of #424).

    ``organizer_side_candidates`` offers every approved volunteer, so the
    digest mails them a queue link; the gates have to let them in.
    """

    def test_queue_and_ticking_work_and_the_row_does_not_link_away(
        self, client, volunteer, organizer, people, conference
    ):
        item = people["items"]["Ada", "promo"]
        assign_item(item, volunteer, actor=organizer)
        client.force_login(volunteer)
        content = client.get(QUEUE).content.decode()
        assert "Promo materials" in content
        # Named, not linked: they may not open the presenter page.
        assert "Ada" in content
        assert people["ada"].get_absolute_url() not in content
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]),
            {"status": "DONE", "next": QUEUE},
        )
        assertRedirects(response, QUEUE)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE and item.completed_by == volunteer
        # Their last item is done; the queue still opens, so they can reopen it.
        assert "Nothing assigned to you" in client.get(QUEUE).content.decode()

    def test_an_approved_team_member_sees_and_ticks_a_team_item(
        self, client, volunteer, people, conference, design_team
    ):
        """The digest mails a team item to every approved member, so the
        gate and the item check have to admit them too (review of #425)."""
        VolunteerProfile.objects.get(user=volunteer, conference=conference).teams.add(
            design_team
        )
        item = people["items"]["Ada", "promo"]
        assign_item(item, team=design_team)
        client.force_login(volunteer)
        content = client.get(QUEUE).content.decode()
        assert "Promo materials" in content and "via the Design team" in content
        response = client.post(
            reverse("speakers:item_status", args=[item.pk]),
            {"status": "DONE", "next": QUEUE},
        )
        assertRedirects(response, QUEUE)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE and item.completed_by == volunteer
        # Reassigning is still organizer-only.
        assert (
            client.post(
                reverse("speakers:item_assign", args=[item.pk]),
                {"owner": f"user:{volunteer.pk}"},
            ).status_code
            == 403
        )

    def test_a_pending_team_member_is_not_on_the_team_yet(
        self, client, people, conference, design_team
    ):
        """Mia is on the team but her application is pending: no queue, no
        tick, and the digest does not reach her either."""
        mia = User.objects.get(username="mia")
        item = people["items"]["Ada", "promo"]
        assign_item(item, team=design_team)
        client.force_login(mia)
        assert client.get(QUEUE).status_code == 403
        assert (
            client.post(
                reverse("speakers:item_status", args=[item.pk]), {"status": "DONE"}
            ).status_code
            == 403
        )
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO

    def test_a_team_i_am_not_on_is_not_mine(
        self, client, volunteer, people, conference, design_team
    ):
        item = people["items"]["Ada", "promo"]
        assign_item(item, team=design_team)
        client.force_login(volunteer)  # approved, but not on the Design team
        assert client.get(QUEUE).status_code == 403

    def test_nobody_is_an_assignee(self, conference, people, design_team):
        """Both predicates answer for a signed-out visitor, and for a page
        rendered when no edition is active."""
        anonymous = AnonymousUser()
        assert is_speaker_assignee(anonymous, conference) is False
        assert list(approved_teams(anonymous, conference)) == []
        assert list(approved_teams(AnonymousUser(), None)) == []

    def test_the_volunteer_hub_offers_the_queue(self, client, volunteer, people):
        item = people["items"]["Ada", "promo"]
        assign_item(item, volunteer)
        client.force_login(volunteer)
        content = client.get(reverse("volunteer:index")).content.decode()
        assert "My speaker tasks" in content and QUEUE in content

    def test_an_item_that_is_not_theirs_is_refused(self, client, volunteer, people):
        assign_item(people["items"]["Ada", "promo"], volunteer)
        client.force_login(volunteer)
        other = people["items"]["Grace", "promo"]
        response = client.post(
            reverse("speakers:item_status", args=[other.pk]), {"status": "DONE"}
        )
        assert response.status_code == 403
        other.refresh_from_db()
        assert other.status == ItemStatus.TODO

    def test_they_neither_reassign_nor_read_the_rest_of_the_module(
        self, client, volunteer, people
    ):
        item = people["items"]["Ada", "promo"]
        assign_item(item, volunteer)
        client.force_login(volunteer)
        assert (
            client.post(
                reverse("speakers:item_assign", args=[item.pk]),
                {"assignee": volunteer.pk},
            ).status_code
            == 403
        )
        assert client.get(BOARD).status_code == 403
        assert client.get(people["ada"].get_absolute_url()).status_code == 403

    def test_a_volunteer_with_no_item_still_has_no_queue(
        self, client, volunteer, people
    ):
        client.force_login(volunteer)
        assert client.get(QUEUE).status_code == 403
        content = client.get(reverse("volunteer:index")).content.decode()
        assert "My speaker tasks" not in content


@pytest.mark.django_db
class TestTeamOwnership:
    def test_assign_to_team_clears_person_and_back(
        self, client, organizer, people, liaison, design_team
    ):
        item = people["items"]["Ada", "promo"]
        client.force_login(organizer)
        url = reverse("speakers:item_assign", args=[item.pk])
        response = client.post(
            url, {"owner": f"team:{design_team.pk}"}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.team == design_team and item.assignee is None
        assert item.owner_label == "Design team"
        assert (
            "→ Design team"
            in ActivityLog.objects.filter(action="checklist.assigned")
            .latest("id")
            .message
        )
        html = response.content.decode()
        assert f'value="team:{design_team.pk}"' in html and "selected" in html
        client.post(url, {"owner": f"user:{liaison.pk}"})
        item.refresh_from_db()
        assert item.assignee == liaison and item.team is None

    def test_queue_includes_my_teams_items(
        self, client, liaison, people, conference, design_team
    ):
        ada = people["ada"]
        team_item = add_adhoc_item(
            conference, "Team job", ItemOwner.ORGANIZER, presenter=ada, team=design_team
        )
        other_team = Team.objects.create(
            conference=conference, short_name="Media", description="m"
        )
        add_adhoc_item(
            conference, "Not mine", ItemOwner.ORGANIZER, presenter=ada, team=other_team
        )
        client.force_login(liaison)
        response = client.get(QUEUE)
        titles = [i.title for i in response.context["items"]]
        assert "Team job" in titles and "Not mine" not in titles
        assert "via the Design team" in response.content.decode()
        assert team_item in response.context["items"]

    def test_one_off_item_for_a_team(self, client, organizer, people, design_team):
        ada = people["ada"]
        client.force_login(organizer)
        client.post(
            reverse("speakers:presenter_add_item", args=[ada.slug]),
            {
                "title": "Poster",
                "owner_kind": ItemOwner.ORGANIZER,
                "owner": f"team:{design_team.pk}",
            },
        )
        item = ada.checklist_items.get(title="Poster")
        assert item.team == design_team and item.assignee is None
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "Design team" in content
        assert "Design team" in client.get(BOARD, {"tab": "organizer"}).content.decode()


@pytest.mark.django_db
class TestSessionPageChecklists:
    def test_session_page_shows_checklists_per_presenter_and_session_items(
        self, client, organizer, people, conference, liaison
    ):
        session, ada = people["session"], people["ada"]
        session_item = add_adhoc_item(
            conference,
            "Edit the recording",
            ItemOwner.ORGANIZER,
            session=session,
            assignee=liaison,
        )
        add_adhoc_item(
            conference, "General thing", ItemOwner.SPEAKER, presenter=ada
        )  # no session
        client.force_login(organizer)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "Checklists for this session" in content
        assert f'data-checklist-presenter="{ada.pk}"' in content
        assert "Update bio" in content  # tied to this session
        assert "Promo materials" not in content  # Ada's, but not tied to a session
        assert "Edit the recording" in content and "General thing" not in content
        assert reverse("speakers:item_assign", args=[session_item.pk]) in content
        assert reverse("speakers:session_add_item", args=[session.slug]) in content
        # Mary is on no session here: no group for her.
        assert f'data-checklist-presenter="{people["mary"].pk}"' not in content

    def test_add_session_item(self, client, organizer, people, liaison):
        session = people["session"]
        client.force_login(organizer)
        url = reverse("speakers:session_add_item", args=[session.slug])
        response = client.post(
            url,
            {
                "title": "Cut the trailer",
                "owner_kind": ItemOwner.ORGANIZER,
                "owner": f"user:{liaison.pk}",
            },
        )
        assertRedirects(response, session.get_absolute_url())
        item = session.checklist_items.get(title="Cut the trailer")
        assert item.presenter is None and item.assignee == liaison
        response = client.post(
            url, {"title": "", "owner_kind": ItemOwner.ORGANIZER}, follow=True
        )
        assert "give it a title" in response.content.decode()

    def test_liaison_cannot_add_session_item(self, client, liaison, people):
        client.force_login(liaison)
        url = reverse("speakers:session_add_item", args=[people["session"].slug])
        assert (
            client.post(
                url, {"title": "x", "owner_kind": ItemOwner.ORGANIZER}
            ).status_code
            == 403
        )

    def test_empty_session_checklists(self, client, organizer, conference, enabled):
        session = make_session(conference)
        client.force_login(organizer)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "No presenter checklists yet" in content
        assert "No session-level items" in content
