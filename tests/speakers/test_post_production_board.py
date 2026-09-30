"""The post-production tab of the checklist board (design §4.2, task 5.5)
and the Videos column on the sessions list."""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from speakers.board import build_post_production_board
from speakers.checklists import (
    assign_item,
    block_item,
    complete_item,
    instantiate_session_checklist,
)
from speakers.constants import (
    Delivery,
    ItemStatus,
    MediaKind,
    MediaStatus,
    SessionStatus,
)
from speakers.models import ChecklistItem, MediaAsset
from speakers.seeds import seed_checklists
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

BOARD = reverse("speakers:checklist_board")
EXPORT = reverse("speakers:checklist_board_export")
SESSIONS = reverse("speakers:session_list")


@pytest.fixture
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def liaison(db, conference):
    user = User.objects.create_user("lena", email="lena@x.org", first_name="Lena")
    VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    return user


def pyjam(conference, title, presenter, **kwargs):
    session = make_session(conference, title=title, kind="PYJAM", **kwargs)
    add_presenter(session, presenter, confirmed=True)
    instantiate_session_checklist(session)
    return session


def video(session, kind=MediaKind.RAW_VIDEO, **kwargs):
    kwargs.setdefault("status", MediaStatus.READY)
    kwargs.setdefault("storage_key", "k")
    return MediaAsset.objects.create(session=session, kind=kind, **kwargs)


def item(session, title):
    return ChecklistItem.objects.get(session=session, presenter=None, title=title)


@pytest.fixture
def world(conference, liaison, organizer):
    """Two PyJam sets with the seeded pipeline (Ada's liaised by Lena, over
    the limit and blocked; Grace's with a final cut in), a live talk, and
    a set that is only proposed."""
    make_settings(conference, translation_languages=["pt-br"])
    seed_checklists(conference)
    ada = make_presenter(conference, display_name="Ada", liaison=liaison)
    grace = make_presenter(conference, display_name="Grace")
    loud = pyjam(conference, "Loud set", ada, language="en")
    quiet = pyjam(conference, "Quiet set", grace, language="en")
    video(loud, version=2, duration_seconds=11 * 60)
    block_item(
        item(loud, "Check video length is within limit"),
        "Video is 1:00 over the 10-minute limit (v2).",
    )
    video(quiet, version=1, duration_seconds=5 * 60)
    video(quiet, kind=MediaKind.PROCESSED_VIDEO, version=1)
    complete_item(item(quiet, "Transcribe"), manual=False)
    assign_item(item(quiet, "Review transcript"), assignee=liaison)
    talk = make_session(conference, title="A talk", kind="TALK")
    add_presenter(talk, grace, confirmed=True)
    proposed = make_session(
        conference, title="Maybe", kind="PYJAM", status=SessionStatus.PROPOSED
    )
    return {
        "loud": loud,
        "quiet": quiet,
        "talk": talk,
        "proposed": proposed,
        "ada": ada,
    }


@pytest.mark.django_db
class TestBoard:
    def test_rows_columns_and_videos(self, organizer, world):
        board = build_post_production_board(world["loud"].conference, organizer)
        assert [row["session"].title for row in board["rows"]] == [
            "Loud set",
            "Quiet set",
        ]
        assert board["columns"][:4] == [
            "Record intro video (MC)",
            "Record outro video (MC)",
            "Review audio and video quality",
            "Check video length is within limit",
        ]
        assert "Translate (pt-br)" in board["columns"]
        loud, quiet = board["rows"]
        assert loud["blocked"] == 1 and "1:00 over" in loud["blocked_note"]
        assert loud["raw"].version == 2 and loud["final"] is None
        assert loud["presenters"] == ["Ada"]
        assert quiet["blocked"] == 0 and quiet["final"].version == 1
        cells = dict(zip(board["columns"], quiet["cells"]))
        assert cells["Transcribe"][1] == "cell-done"
        assert cells["Check video length is within limit"][0].status == ItemStatus.DONE
        assert cells["Review transcript"][0].owner_label == "Lena"

    def test_blocked_first_then_name_sort(self, organizer, world):
        conference = world["loud"].conference
        titles = lambda sort: [  # noqa: E731
            r["session"].title
            for r in build_post_production_board(conference, organizer, sort=sort)[
                "rows"
            ]
        ]
        assert titles("overdue") == ["Loud set", "Quiet set"]
        complete_item(
            item(world["loud"], "Check video length is within limit"), manual=False
        )
        # Nothing blocked: the row with more overdue items leads. Loud has
        # every seeded line still open; Quiet's final cut is in.
        assert titles("overdue") == ["Loud set", "Quiet set"]
        for title in ("Record intro video (MC)", "Record outro video (MC)"):
            complete_item(item(world["loud"], title), manual=False)
        complete_item(item(world["loud"], "Review audio and video quality"))
        assert titles("overdue") == ["Quiet set", "Loud set"]
        assert titles("name") == ["Loud set", "Quiet set"]

    def test_the_page_shows_the_blocked_row_and_the_videos(
        self, client, organizer, world
    ):
        client.force_login(organizer)
        response = client.get(BOARD, {"tab": "post_production"})
        assert response.status_code == 200
        assert response.context["tab"] == "POST_PRODUCTION"
        html = response.content.decode()
        assert 'href="?tab=post_production' in html
        assert (
            'class="table-danger"' in html and "1:00 over the 10-minute limit" in html
        )
        assert "raw</a>" not in html  # the version travels with the word
        assert "raw v2" in html and "11 min 00 s" in html and "no final cut" in html
        assert "final cut v1" in html
        assert "Lena" in html and "unassigned" in html
        assert (
            reverse(
                "speakers:item_detail", args=[item(world["quiet"], "Transcribe").pk]
            )
            in html
        )
        assert "A talk" not in html and "Maybe" not in html

    def test_liaison_sees_only_their_sessions(self, client, liaison, world):
        client.force_login(liaison)
        html = client.get(BOARD, {"tab": "post_production"}).content.decode()
        assert "Loud set" in html and "Quiet set" not in html

    def test_query_count_does_not_grow_with_sessions(
        self, client, organizer, world, conference
    ):
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(BOARD, {"tab": "post_production"})
        for n in range(4):
            session = pyjam(conference, f"Set {n}", make_presenter(conference))
            video(session, version=1)
            video(session, kind=MediaKind.PROCESSED_VIDEO, version=1)
            assign_item(item(session, "Transcribe"), assignee=organizer)
        with CaptureQueriesContext(connection) as after:
            client.get(BOARD, {"tab": "post_production"})
        assert len(after) == len(before)

    def test_empty_board(self, client, organizer, conference):
        make_settings(conference)
        client.force_login(organizer)
        html = client.get(BOARD, {"tab": "post-production"}).content.decode()
        assert "No pre-recorded sessions with post-production items yet" in html

    def test_csv_export(self, client, organizer, world):
        client.force_login(organizer)
        response = client.get(EXPORT, {"tab": "post_production"})
        assert (
            response["Content-Disposition"].endswith(
                'checklists-post_production-2026.csv"'
            )
            or "post_production" in response["Content-Disposition"]
        )
        lines = response.content.decode().splitlines()
        assert lines[1].startswith("Session,Presenters,Raw video,Final cut,Blocked")
        assert "Loud set,Ada,v2 (11:00),,Video is 1:00 over" in lines[2]
        assert "Quiet set,Grace,v1 (5:00),v1," in lines[3]
        assert "Done" in lines[3] and "To do (Lena)" in lines[3]


@pytest.mark.django_db
class TestVideosColumn:
    def test_the_sessions_list_says_where_each_video_stands(
        self, client, organizer, world
    ):
        client.force_login(organizer)
        response = client.get(SESSIONS)
        assert response.status_code == 200
        html = response.content.decode()
        assert "raw v2 · 11 min 00 s" in html and "no final cut" in html
        assert "raw v1 · 5 min 00 s" in html and "final cut v1" in html
        rows = {s.title: s for s in response.context["table"].data}
        assert rows["A talk"].raw_video_version is None
        assert rows["A talk"].delivery == Delivery.LIVE

    def test_no_raw_video_yet(self, client, organizer, conference):
        make_settings(conference)
        pyjam(conference, "Silent set", make_presenter(conference))
        client.force_login(organizer)
        html = client.get(SESSIONS).content.decode()
        assert "no raw video" in html

    def test_query_count_does_not_grow_with_videos(
        self, client, organizer, world, conference
    ):
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(SESSIONS)
        for n in range(4):
            session = pyjam(conference, f"Set {n}", make_presenter(conference))
            video(session, version=1, duration_seconds=60)
            video(session, version=2, duration_seconds=61)
            video(session, kind=MediaKind.PROCESSED_VIDEO, version=1)
        with CaptureQueriesContext(connection) as after:
            client.get(SESSIONS)
        assert len(after) == len(before)
