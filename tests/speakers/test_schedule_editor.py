"""The schedule editor and its one mutation endpoint (task 4.2, design §10)."""

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from speakers.constants import SessionStatus
from speakers.models import ActivityLog, ScheduleSlot, Session, TransitionError
from speakers.program_types import session_type
from speakers.schedule import (
    ALL_ROOMS_COLUMN,
    FIRST_ROOM_COLUMN,
    FIRST_TIME_ROW,
    _window,
    day_bounds,
    grid_for_day,
    schedule_days,
    timezone_options,
)

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_room,
    make_session,
    make_settings,
    make_slot,
)

EDITOR = reverse("speakers:schedule_editor")
T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


@pytest.fixture
def liaison(db):
    return User.objects.create_user(username="liaison", email="liaison@example.com")


def slot_url(session):
    return reverse("speakers:session_slot", args=[session.slug])


def send(client, session, payload, method="patch"):
    call = getattr(client, method)
    return call(slot_url(session), json.dumps(payload), content_type="application/json")


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_redirected(self, client, enabled):
        assertRedirects(
            client.get(EDITOR), reverse("account_login") + "?next=" + EDITOR
        )

    def test_plain_user_forbidden(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(EDITOR).status_code == 403

    def test_liaison_forbidden(self, client, liaison, enabled, conference):
        make_presenter(conference, liaison=liaison)
        client.force_login(liaison)
        assert client.get(EDITOR).status_code == 403
        assert (
            send(
                client, make_session(conference), {"start": T0.isoformat()}
            ).status_code
            == 403
        )

    def test_module_off_is_404(self, client, organizer):
        client.force_login(organizer)
        assert client.get(EDITOR).status_code == 404

    def test_organizer_sees_the_grid(self, client, organizer, enabled):
        client.force_login(organizer)
        response = client.get(EDITOR)
        assert response.status_code == 200
        assert "Unscheduled" in response.content.decode()


@pytest.mark.django_db
class TestEditorPage:
    def test_day_tabs_span_the_conference(self, client, organizer, enabled, conference):
        conference.start_date = date(2026, 12, 4)
        conference.end_date = date(2026, 12, 6)
        conference.save()
        make_slot(
            make_session(conference, kind="BREAK"), start_utc=T0 + timedelta(days=30)
        )
        client.force_login(organizer)
        response = client.get(EDITOR)
        assert response.context["days"] == [
            date(2026, 12, 4),
            date(2026, 12, 5),
            date(2026, 12, 6),
            date(2027, 1, 4),
        ]
        assert response.context["day"] == date(2026, 12, 4)

    def test_day_falls_back_when_unknown(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        first = client.get(EDITOR).context["day"]
        assert client.get(EDITOR, {"day": "not-a-day"}).context["day"] == first
        assert client.get(EDITOR, {"day": "1999-01-01"}).context["day"] == first

    def test_board_partial(self, client, organizer, enabled, conference):
        """The refresh region holds the grid AND the sidebar, so placing a
        session updates the Unscheduled list in the same swap."""
        make_session(conference, title="Still waiting")
        client.force_login(organizer)
        content = client.get(EDITOR, {"board": "1"}).content.decode()
        assert "schedule-grid" in content
        assert "Still waiting" in content
        assert "Unscheduled" in content
        assert "<h1" not in content

    def test_cards_sit_where_their_slot_says(self, conference, enabled):
        conference.start_date = conference.end_date = date(2026, 12, 5)
        conference.save()
        room = make_room(conference)
        talk = make_session(conference, kind="TALK")
        make_slot(talk, room=room, start_utc=T0)
        band = make_session(conference, kind="BREAK")
        make_slot(band, start_utc=T0 + timedelta(hours=2))
        grid = grid_for_day(conference, date(2026, 12, 5), full_day=True)
        by_session = {card["session"].pk: card for card in grid["cards"]}
        placed = by_session[talk.pk]
        assert placed["row"] == FIRST_TIME_ROW + 14 * 4
        assert placed["span"] == 2
        assert placed["start_column"] == FIRST_ROOM_COLUMN
        assert placed["end_column"] == FIRST_ROOM_COLUMN + 1
        spanning = by_session[band.pk]
        assert spanning["is_band"] is True
        assert spanning["start_column"] == ALL_ROOMS_COLUMN
        assert spanning["end_column"] == grid["last_column"]

    def test_midnight_crosser_is_clipped(self, conference, enabled):
        session = make_session(conference)
        make_slot(session, start_utc=datetime(2026, 12, 5, 23, 30, tzinfo=timezone.utc))
        grid = grid_for_day(conference, date(2026, 12, 5), full_day=True)
        card = grid["cards"][0]
        assert card["row"] == FIRST_TIME_ROW + 94
        assert card["span"] == 2

    def test_a_retired_room_with_a_slot_keeps_its_lane(self, conference, enabled):
        room = make_room(conference, name="old-stage", is_active=False)
        make_slot(make_session(conference), room=room, start_utc=T0)
        grid = grid_for_day(conference, date(2026, 12, 5))
        lane = [lane for lane in grid["lanes"] if lane["pk"] == room.pk]
        assert lane and lane[0]["name"] == "old-stage (retired)"
        assert grid["cards"][0]["start_column"] == lane[0]["column"]
        assert grid["cards"][0]["is_band"] is False

    def test_double_booking_is_flagged_on_both_cards(
        self, client, organizer, enabled, conference
    ):
        ada = make_presenter(conference, display_name="Ada")
        first = make_session(conference, title="First")
        second = make_session(conference, title="Second")
        add_presenter(first, ada)
        add_presenter(second, ada)
        make_slot(first, room=make_room(conference), start_utc=T0)
        make_slot(second, room=make_room(conference), start_utc=T0)
        client.force_login(organizer)
        content = client.get(EDITOR, {"day": "2026-12-05"}).content.decode()
        assert "Ada is also in" in content
        assert content.count("schedule-warned") == 2

    def test_unscheduled_sidebar(self, client, organizer, enabled, conference):
        waiting = make_session(conference, title="Still waiting")
        cancelled = make_session(conference, title="Called off")
        cancelled.cancel()
        placed = make_session(conference, title="Already placed")
        make_slot(placed, start_utc=T0 + timedelta(days=1))
        client.force_login(organizer)
        titles = [s.title for s in client.get(EDITOR).context["unscheduled"]]
        assert waiting.title in titles
        assert cancelled.title not in titles
        assert placed.title not in titles

    def test_timezone_options(self, conference, enabled):
        enabled.conference_timezone = "America/Vancouver"
        enabled.save()
        ada = make_presenter(conference, display_name="Ada", timezone="Africa/Lagos")
        twin = make_presenter(conference, display_name="Grace", timezone="Africa/Lagos")
        make_presenter(conference, timezone="Asia/Tokyo")
        session = make_session(conference)
        add_presenter(session, ada)
        add_presenter(session, twin)
        make_slot(session, start_utc=T0)
        values = timezone_options(conference)
        assert values[0] == ("UTC", "UTC")
        assert ("America/Vancouver", "America/Vancouver") in values
        lagos = [v for v in values if v[0] == "Africa/Lagos"]
        assert lagos == [("Africa/Lagos", "Africa/Lagos (Ada)")]
        assert all(v[0] != "Asia/Tokyo" for v in values)

    def test_days_fall_back_to_today(self, conference, enabled):
        conference.conference_date = None
        conference.save()
        assert schedule_days(conference) == [date.today()]

    def test_program_item_created_inline(self, client, organizer, enabled, conference):
        conference.start_date = conference.end_date = date(2026, 12, 5)
        conference.save()
        client.force_login(organizer)
        kind = session_type(conference, "BREAK")
        response = client.post(
            EDITOR + "?day=2026-12-05",
            {"kind": kind.pk, "title": "Lunch", "summary_md": ""},
        )
        assertRedirects(response, EDITOR + "?day=2026-12-05")
        lunch = Session.objects.get(title="Lunch")
        assert lunch.status == SessionStatus.CONFIRMED
        assert ActivityLog.objects.filter(
            action="session.created", object_id=lunch.pk
        ).exists()

    def test_program_item_errors_rerender(self, client, organizer, enabled):
        client.force_login(organizer)
        response = client.post(EDITOR, {"title": ""})
        assert response.status_code == 200
        assert response.context["program_item_form"].errors

    def test_query_count_is_flat(self, client, organizer, enabled, conference):
        room = make_room(conference)
        make_slot(make_session(conference), room=room, start_utc=T0)
        make_session(conference, title="Waiting A")
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(EDITOR, {"day": "2026-12-05"})
        for n in range(4):
            session = make_session(conference, title=f"Extra {n}")
            add_presenter(session, make_presenter(conference))
            make_slot(session, room=room, start_utc=T0 + timedelta(hours=2 * (n + 1)))
            make_session(conference, title=f"Waiting {n}")
        with CaptureQueriesContext(connection) as after:
            client.get(EDITOR, {"day": "2026-12-05"})
        assert len(after) == len(before)


@pytest.mark.django_db
class TestSlotPatch:
    def test_placing_is_a_draft_until_the_publish(
        self, client, organizer, enabled, conference
    ):
        """The grid is the organizers' scratchpad (§10.1): placing a
        confirmed session changes nothing a speaker sees."""
        room = make_room(conference)
        session = make_session(conference, title="Ready", kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        client.force_login(organizer)
        response = send(
            client,
            session,
            {"room": room.pk, "start": T0.isoformat()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["status"] == SessionStatus.CONFIRMED
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED
        assert session.has_published_slot is False
        slot = session.slot
        assert slot.room == room
        assert slot.end_utc == T0 + timedelta(minutes=60)
        assert ActivityLog.objects.filter(
            action="slot.placed", object_id=session.pk
        ).exists()

    def test_placing_a_draft_leaves_its_status(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference)
        client.force_login(organizer)
        assert send(client, session, {"start": T0.isoformat()}).status_code == 200
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT
        assert session.has_slot is True

    def test_conflict_is_refused_as_json(self, client, organizer, enabled, conference):
        room = make_room(conference)
        make_slot(
            make_session(conference, title="Sitting here"),
            room=room,
            start_utc=T0,
        )
        session = make_session(conference)
        client.force_login(organizer)
        response = send(client, session, {"room": room.pk, "start": T0.isoformat()})
        assert response.status_code == 400
        assert "Sitting here" in response.json()["errors"][0]
        assert not ScheduleSlot.objects.filter(session=session).exists()

    def test_moving_keeps_the_length(self, client, organizer, enabled, conference):
        session = make_session(conference)
        make_slot(session, start_utc=T0, end_utc=T0 + timedelta(minutes=45))
        client.force_login(organizer)
        later = T0 + timedelta(hours=3)
        assert send(client, session, {"start": later.isoformat()}).status_code == 200
        slot = ScheduleSlot.objects.get(session=session)
        assert slot.end_utc - slot.start_utc == timedelta(minutes=45)
        assert ActivityLog.objects.filter(
            action="slot.moved", object_id=session.pk
        ).exists()

    def test_resize_sets_the_duration(self, client, organizer, enabled, conference):
        session = make_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        assert send(client, session, {"duration": 30}).status_code == 200
        slot = ScheduleSlot.objects.get(session=session)
        assert slot.end_utc == T0 + timedelta(minutes=30)

    def test_short_or_broken_duration_is_refused(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        assert send(client, session, {"duration": 10}).status_code == 400
        assert send(client, session, {"duration": "soon"}).status_code == 400

    def test_explicit_end_and_recomputed_end(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference, kind="TALK")
        make_slot(session, start_utc=T0, end_utc=T0 + timedelta(minutes=45))
        client.force_login(organizer)
        end = T0 + timedelta(minutes=75)
        assert send(client, session, {"end": end.isoformat()}).status_code == 200
        assert ScheduleSlot.objects.get(session=session).end_utc == end
        assert send(client, session, {"end": None}).status_code == 200
        assert ScheduleSlot.objects.get(session=session).end_utc == T0 + timedelta(
            minutes=30
        )

    def test_room_changes_and_the_all_rooms_lane(
        self, client, organizer, enabled, conference
    ):
        room = make_room(conference)
        session = make_session(conference, kind="BREAK")
        make_slot(session, room=room, start_utc=T0)
        client.force_login(organizer)
        assert send(client, session, {"room": None}).status_code == 200
        assert ScheduleSlot.objects.get(session=session).room is None

    def test_unknown_or_foreign_room_is_refused(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference)
        client.force_login(organizer)
        response = send(client, session, {"room": 9999, "start": T0.isoformat()})
        assert response.status_code == 400
        assert "room" in response.json()["errors"][0]

    def test_bad_bodies_are_refused(self, client, organizer, enabled, conference):
        session = make_session(conference)
        client.force_login(organizer)
        url = slot_url(session)
        assert (
            client.patch(url, "not json", content_type="application/json").status_code
            == 400
        )
        assert (
            client.patch(url, "[1]", content_type="application/json").status_code == 400
        )
        assert send(client, session, {"start": "whenever"}).status_code == 400
        assert send(client, session, {"duration": 30}).status_code == 400

    def test_naive_start_is_read_as_utc(self, client, organizer, enabled, conference):
        session = make_session(conference)
        client.force_login(organizer)
        assert (
            send(client, session, {"start": "2026-12-05T14:00:00"}).status_code == 200
        )
        assert ScheduleSlot.objects.get(session=session).start_utc == T0

    def test_a_proposal_cannot_be_placed(self, client, organizer, enabled, conference):
        session = make_session(conference, status=SessionStatus.PROPOSED)
        client.force_login(organizer)
        response = send(client, session, {"start": T0.isoformat()})
        assert response.status_code == 400
        assert "not on the program" in response.json()["errors"][0]

    def test_response_carries_presenter_warnings(
        self, client, organizer, enabled, conference
    ):
        ada = make_presenter(conference, display_name="Ada")
        first = make_session(conference, title="First")
        second = make_session(conference, title="Second")
        add_presenter(first, ada)
        add_presenter(second, ada)
        make_slot(first, room=make_room(conference), start_utc=T0)
        client.force_login(organizer)
        response = send(
            client,
            second,
            {"room": make_room(conference).pk, "start": T0.isoformat()},
        )
        assert response.json()["warnings"] == ["Ada is also in “First”"]


@pytest.mark.django_db
class TestSlotDelete:
    def test_removing_a_working_slot_leaves_the_published_schedule(
        self, client, organizer, enabled, conference
    ):
        """Un-gridding is a draft edit: speakers keep their snapshot and
        the status until the next publish (§10.1)."""
        session = make_session(conference, kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        session.schedule()
        client.force_login(organizer)
        response = send(client, session, {}, method="delete")
        assert response.status_code == 200
        session.refresh_from_db()
        assert session.status == SessionStatus.SCHEDULED
        assert session.has_slot is False
        assert session.has_published_slot is True
        assert ActivityLog.objects.filter(
            action="slot.removed", object_id=session.pk
        ).exists()

    def test_a_draft_keeps_its_status(self, client, organizer, enabled, conference):
        session = make_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        assert send(client, session, {}, method="delete").status_code == 200
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT

    def test_public_sessions_keep_their_slot(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference, kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        session.schedule()
        session.publish()
        client.force_login(organizer)
        response = send(client, session, {}, method="delete")
        assert response.status_code == 400
        assert session.has_slot is True

    def test_no_slot_is_404(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = send(client, make_session(conference), {}, method="delete")
        assert response.status_code == 404


@pytest.mark.django_db
class TestUnscheduleTransition:
    def test_only_scheduled_comes_back(self, conference):
        session = make_session(conference, kind="BREAK", status=SessionStatus.SCHEDULED)
        session.unschedule()
        assert session.status == SessionStatus.CONFIRMED
        with pytest.raises(TransitionError):
            make_session(conference).unschedule()


@pytest.mark.django_db
class TestCellPanel:
    """Clicking an empty cell adds something right there (the panel's
    server half: the JS fills start and room from the cell)."""

    def test_the_board_offers_the_panel(self, client, organizer, enabled, conference):
        make_session(conference, title="Still waiting")
        client.force_login(organizer)
        content = client.get(EDITOR, {"board": "1"}).content.decode()
        assert "schedule-cell-panel" in content
        assert "schedule-place-option" in content
        assert "data-room-name" in content

    def test_a_program_item_lands_on_the_clicked_cell(
        self, client, organizer, enabled, conference
    ):
        room = make_room(conference)
        client.force_login(organizer)
        response = client.post(
            EDITOR + "?day=2026-12-05",
            {
                "kind": session_type(conference, "BREAK").pk,
                "title": "Lunch here",
                "start": T0.isoformat(),
                "room": room.pk,
            },
        )
        assertRedirects(response, EDITOR + "?day=2026-12-05")
        lunch = Session.objects.get(title="Lunch here")
        assert lunch.status == SessionStatus.CONFIRMED
        assert lunch.has_published_slot is False
        assert lunch.slot.room == room
        assert lunch.slot.start_utc == T0
        assert ActivityLog.objects.filter(
            action="slot.placed", object_id=lunch.pk
        ).exists()

    def test_no_room_means_every_room(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        client.post(
            EDITOR,
            {
                "kind": session_type(conference, "SOCIAL").pk,
                "title": "Hallway",
                "start": T0.isoformat(),
                "room": "",
            },
        )
        hallway = Session.objects.get(title="Hallway")
        assert hallway.slot.room is None
        assert hallway.status == SessionStatus.CONFIRMED

    def test_a_refused_window_keeps_the_item_unscheduled(
        self, client, organizer, enabled, conference
    ):
        room = make_room(conference)
        make_slot(make_session(conference), room=room, start_utc=T0)
        client.force_login(organizer)
        response = client.post(
            EDITOR,
            {
                "kind": session_type(conference, "BREAK").pk,
                "title": "Clashing break",
                "start": T0.isoformat(),
                "room": room.pk,
            },
            follow=True,
        )
        clashing = Session.objects.get(title="Clashing break")
        assert clashing.status == SessionStatus.CONFIRMED
        assert clashing.has_slot is False
        assert "could not place it" in response.content.decode()

    def test_a_broken_start_keeps_the_item(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        response = client.post(
            EDITOR,
            {
                "kind": session_type(conference, "BREAK").pk,
                "title": "Sometime",
                "start": "whenever",
            },
            follow=True,
        )
        sometime = Session.objects.get(title="Sometime")
        assert sometime.has_slot is False
        assert "could not place it" in response.content.decode()


@pytest.mark.django_db
class TestUnscheduleAll:
    def test_clears_the_shown_day_only(self, client, organizer, enabled, conference):
        scheduled = make_session(conference, kind="PANEL")
        add_presenter(scheduled, make_presenter(conference), confirmed=True)
        scheduled.confirm()
        make_slot(scheduled, room=make_room(conference), start_utc=T0)
        make_published_slot(scheduled)
        scheduled.schedule()
        draft = make_session(conference)
        make_slot(draft, start_utc=T0 + timedelta(hours=4))
        other_day = make_session(conference)
        make_slot(other_day, start_utc=T0 + timedelta(days=2))
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:schedule_clear_day"), {"day": "2026-12-05"}
        )
        assertRedirects(response, EDITOR + "?day=2026-12-05")
        scheduled.refresh_from_db()
        draft.refresh_from_db()
        assert scheduled.status == SessionStatus.SCHEDULED
        assert scheduled.has_published_slot is True
        assert scheduled.has_slot is False
        assert draft.has_slot is False
        assert draft.status == SessionStatus.DRAFT
        assert other_day.has_slot is True
        assert ActivityLog.objects.filter(action="slot.removed").count() == 2

    def test_published_sessions_keep_their_slot(
        self, client, organizer, enabled, conference
    ):
        published = make_session(conference, kind="PANEL")
        add_presenter(published, make_presenter(conference), confirmed=True)
        published.confirm()
        make_slot(published, start_utc=T0)
        make_published_slot(published)
        published.schedule()
        published.publish()
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:schedule_clear_day"),
            {"day": "2026-12-05"},
            follow=True,
        )
        published.refresh_from_db()
        assert published.status == SessionStatus.PUBLISHED
        assert published.has_slot is True
        assert "kept their slot" in response.content.decode()

    def test_the_button_is_on_the_page(self, client, organizer, enabled):
        client.force_login(organizer)
        content = client.get(EDITOR).content.decode()
        assert "Unschedule all" in content
        assert reverse("speakers:schedule_clear_day") in content

    def test_organizer_only(self, client, liaison, enabled, conference):
        make_presenter(conference, liaison=liaison)
        client.force_login(liaison)
        response = client.post(
            reverse("speakers:schedule_clear_day"), {"day": "2026-12-05"}
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestReviewHardening:
    """The #459 review: strict targets, bounded input, no half-writes."""

    def test_clear_refuses_an_unrecognised_day(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        for value in ("2026-12-20", "garbage", ""):
            response = client.post(
                reverse("speakers:schedule_clear_day"), {"day": value}, follow=True
            )
            assert "nothing was unscheduled" in response.content.decode()
        session.refresh_from_db()
        assert session.has_slot is True
        assert not ActivityLog.objects.filter(action="session.unscheduled").exists()

    def test_a_stale_room_keeps_the_item_off_the_grid(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        for value in ("9999", "abc"):
            response = client.post(
                EDITOR,
                {
                    "kind": session_type(conference, "BREAK").pk,
                    "title": f"Break {value}",
                    "start": T0.isoformat(),
                    "room": value,
                },
                follow=True,
            )
            created = Session.objects.get(title=f"Break {value}")
            assert created.has_slot is False
            assert "could not place it" in response.content.decode()
            assert "does not exist in this edition" in response.content.decode()

    def test_a_retired_room_is_not_droppable(
        self, client, organizer, enabled, conference
    ):
        """The retired lane exists so an old card is not misdrawn, not
        as a target: retirement closes the room (review of #460)."""
        room = make_room(conference, is_active=False)
        session = make_session(conference)
        client.force_login(organizer)
        response = send(client, session, {"room": room.pk, "start": T0.isoformat()})
        assert response.status_code == 400
        assert "does not exist" in response.json()["errors"][0]

    def test_mangled_room_values_answer_400(
        self, client, organizer, enabled, conference
    ):
        session = make_session(conference)
        client.force_login(organizer)
        for value in ("abc", ["1"]):
            response = send(client, session, {"room": value, "start": T0.isoformat()})
            assert response.status_code == 400
            assert "does not exist" in response.json()["errors"][0]
        assert session.has_slot is False

    def test_duration_is_capped_at_a_day(self, client, organizer, enabled, conference):
        session = make_session(conference)
        make_slot(session, start_utc=T0)
        client.force_login(organizer)
        for minutes in (10**9, 10**12, 1441):
            assert send(client, session, {"duration": minutes}).status_code == 400
        end = T0 + timedelta(days=30)
        response = send(client, session, {"end": end.isoformat()})
        assert response.status_code == 400
        assert "longer than a day" in response.json()["errors"][0]
        assert send(client, session, {"duration": 1440}).status_code == 200

    def test_moving_a_public_session_leaves_the_snapshot(
        self, client, organizer, enabled, conference
    ):
        """Even a public session's working slot is a draft: the speakers'
        and the public's times hold until the next publish (§10.1)."""
        session = make_session(conference, kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        make_slot(session, start_utc=T0)
        make_published_slot(session)
        session.schedule()
        session.publish()
        client.force_login(organizer)
        later = T0 + timedelta(hours=2)
        response = send(client, session, {"start": later.isoformat()})
        assert response.status_code == 200
        assert response.json()["warnings"] == []
        session.refresh_from_db()
        assert session.published_slot.start_utc == T0

    def test_the_redirect_day_is_sanitised(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        response = client.post(
            EDITOR + "?day=not-a-day",
            {"kind": session_type(conference, "BREAK").pk, "title": "Pause"},
        )
        assert response.status_code == 302
        assert "not-a-day" not in response.url


@pytest.mark.django_db
class TestTrimmedWindow:
    """The grid shows the program, not the empty night (task 4.6)."""

    def test_the_day_trims_around_the_program(self, conference, enabled):
        session = make_session(conference, kind="TALK")
        make_slot(session, start_utc=T0)
        grid = grid_for_day(conference, date(2026, 12, 5))
        assert grid["trimmed"] is True
        assert grid["rows"][0]["utc"].hour == 13
        assert len(grid["rows"]) == 12
        assert grid["cards"][0]["row"] == FIRST_TIME_ROW + 4

    def test_full_day_on_request_and_when_empty(self, conference, enabled):
        empty = grid_for_day(conference, date(2026, 12, 5))
        assert empty["trimmed"] is False
        assert len(empty["rows"]) == 96
        session = make_session(conference, kind="TALK")
        make_slot(session, start_utc=T0)
        full = grid_for_day(conference, date(2026, 12, 5), full_day=True)
        assert full["trimmed"] is False
        assert len(full["rows"]) == 96
        assert full["cards"][0]["row"] == FIRST_TIME_ROW + 14 * 4

    def test_the_window_clamps_to_the_day(self, conference, enabled):
        early = make_session(conference, kind="TALK")
        make_slot(early, start_utc=datetime(2026, 12, 5, 0, 15, tzinfo=timezone.utc))
        late = make_session(conference, kind="TALK")
        make_slot(late, start_utc=datetime(2026, 12, 5, 23, 30, tzinfo=timezone.utc))
        grid = grid_for_day(conference, date(2026, 12, 5))
        assert grid["trimmed"] is False
        assert len(grid["rows"]) == 96

    def test_a_stray_second_cannot_shift_the_window(self):
        """Review of #462: a 10:00:30 start moved every row time to :30
        seconds and drew a clean 14:00 slot a row early."""
        day_start, day_end = day_bounds(date(2026, 12, 5))

        def at(h, m=0, s=0, us=0):
            return datetime(2026, 12, 5, h, m, s, us, tzinfo=timezone.utc)

        slots = [
            SimpleNamespace(start_utc=at(14), end_utc=at(15)),
            SimpleNamespace(start_utc=at(10, 0, 30), end_utc=at(11, 0, 30)),
        ]
        assert _window(day_start, day_end, slots, False) == (at(9), at(16))
        slots.append(SimpleNamespace(start_utc=at(14), end_utc=at(15, 0, 0, 1)))
        assert _window(day_start, day_end, slots, False)[1] == at(17)

    def test_slots_store_whole_minutes(self, conference, enabled):
        """The admin form and the PATCH endpoint accept seconds; the
        stored slot drops them, so the grid stays on its quarter-hours."""
        clean = make_session(conference, kind="TALK")
        make_slot(clean, start_utc=T0)
        stray = make_session(conference, kind="TALK")
        slot = make_slot(
            stray,
            start_utc=datetime(2026, 12, 5, 10, 0, 30, tzinfo=timezone.utc),
            end_utc=datetime(2026, 12, 5, 11, 0, 30, 5, tzinfo=timezone.utc),
        )
        slot.refresh_from_db()
        assert (slot.start_utc.second, slot.end_utc.second) == (0, 0)
        assert slot.end_utc.microsecond == 0
        grid = grid_for_day(conference, date(2026, 12, 5))
        assert grid["rows"][0]["utc"] == datetime(2026, 12, 5, 9, tzinfo=timezone.utc)
        assert all(row["utc"].second == 0 for row in grid["rows"])
        by_title = {card["session"].pk: card["row"] for card in grid["cards"]}
        assert by_title[clean.pk] == FIRST_TIME_ROW + 5 * 4

    def test_a_trim_that_saves_little_is_not_offered(self, conference, enabled):
        """Slots near both midnight ends would trim four rows: a no-op
        with a toggle link attached, so the whole day renders instead."""
        early = make_session(conference, kind="TALK")
        make_slot(early, start_utc=datetime(2026, 12, 5, 0, 15, tzinfo=timezone.utc))
        late = make_session(conference, kind="TALK")
        make_slot(late, start_utc=datetime(2026, 12, 5, 21, 30, tzinfo=timezone.utc))
        grid = grid_for_day(conference, date(2026, 12, 5))
        assert grid["trimmed"] is False
        assert len(grid["rows"]) == 96

    def test_the_page_offers_the_toggle_and_the_density_switch(
        self, client, organizer, enabled, conference
    ):
        make_slot(make_session(conference), start_utc=T0)
        client.force_login(organizer)
        content = client.get(EDITOR, {"day": "2026-12-05"}).content.decode()
        assert "Show the whole day" in content
        assert "schedule-density" in content
        assert "data-rows=" in content
        content = client.get(
            EDITOR, {"day": "2026-12-05", "full": "1"}
        ).content.decode()
        assert "Trim to the program" in content
