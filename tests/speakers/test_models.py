from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError

from portal.models import Conference
from speakers.constants import (
    Delivery,
    PremiereLocation,
    PresenterRole,
    SessionKind,
    SessionStatus,
)
from speakers.models import (
    ActivityLog,
    DiscordChannel,
    Presenter,
    ScheduleSlot,
    Session,
    SessionPresenter,
    TransitionError,
    validate_timezone,
)

from .factories import (
    add_presenter,
    make_channel,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)


@pytest.fixture
def other_conference(db):
    return Conference.objects.create(year=2024, name="PyLadiesCon 2024", slug="2024")


@pytest.mark.django_db
class TestIsolation:
    """Cross-edition queries return nothing (design §7)."""

    def test_sessions_scoped(self, conference, other_conference):
        make_session(conference, title="Ours")
        make_session(other_conference, title="Theirs")
        assert list(conference.sessions.values_list("title", flat=True)) == ["Ours"]
        assert list(other_conference.sessions.values_list("title", flat=True)) == [
            "Theirs"
        ]

    def test_presenters_scoped(self, conference, other_conference):
        make_presenter(conference, display_name="Ada")
        make_presenter(other_conference, display_name="Grace")
        assert [p.display_name for p in conference.presenters.all()] == ["Ada"]
        assert Session.objects.filter(conference=other_conference).count() == 0

    def test_same_email_allowed_across_editions(self, conference, other_conference):
        make_presenter(conference, email="ada@example.com")
        make_presenter(other_conference, email="ada@example.com")
        assert Presenter.objects.filter(email="ada@example.com").count() == 2

    def test_session_presenter_rejects_mixed_editions(
        self, conference, other_conference
    ):
        session = make_session(conference)
        presenter = make_presenter(other_conference)
        with pytest.raises(ValidationError, match="different editions"):
            add_presenter(session, presenter)
        assert SessionPresenter.objects.count() == 0

    def test_session_presenter_and_slot_inherit_edition(self, conference):
        session = make_session(conference)
        link = add_presenter(session, make_presenter(conference))
        slot = make_slot(session)
        assert link.conference == conference
        assert slot.conference == conference
        assert list(conference.session_presenters.all()) == [link]
        assert list(conference.schedule_slots.all()) == [slot]

    def test_channels_scoped(self, conference, other_conference):
        make_channel(conference, name="stage-1")
        make_channel(other_conference, name="stage-1")
        assert conference.discord_channels.count() == 1
        assert DiscordChannel.objects.count() == 2


@pytest.mark.django_db
class TestSession:
    def test_str_and_slug(self, conference):
        session = make_session(conference, title="Intro to Django!")
        assert str(session) == "Intro to Django!"
        assert session.slug == "intro-to-django"

    def test_slug_unique_per_edition(self, conference, other_conference):
        make_session(conference, title="Same")
        second = make_session(conference, title="Same")
        third = make_session(other_conference, title="Same")
        assert second.slug == "same-2"
        assert third.slug == "same"

    def test_slug_kept_on_resave(self, conference):
        session = make_session(conference, title="Keep me")
        session.title = "Renamed"
        session.save()
        assert session.slug == "keep-me"

    def test_slug_regenerated_when_cleared_ignores_own_row(self, conference):
        session = make_session(conference, title="Keep me")
        session.slug = ""
        session.save()
        assert session.slug == "keep-me"

    def test_slug_for_untitled_symbols(self, conference):
        assert make_session(conference, title="***").slug == "item"

    def test_duration_defaults_by_kind(self, conference):
        assert (
            make_session(conference, kind=SessionKind.WORKSHOP).duration_minutes == 90
        )
        assert make_session(conference, kind=SessionKind.PANEL).duration_minutes == 60
        assert (
            make_session(
                conference, kind=SessionKind.PANEL, duration_minutes=45
            ).duration_minutes
            == 45
        )

    def test_is_content(self, conference):
        assert make_session(conference, kind=SessionKind.PYJAM).is_content is True
        assert make_session(conference, kind=SessionKind.BREAK).is_content is False

    def test_is_pre_recorded(self, conference):
        live = make_session(conference)
        recorded = make_session(conference, delivery=Delivery.PRE_RECORDED)
        assert live.is_pre_recorded is False
        assert recorded.is_pre_recorded is True

    def test_premiere_location_falls_back_to_edition_default(self, conference):
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        assert session.effective_premiere_location == PremiereLocation.DISCORD
        make_settings(conference, default_premiere_location=PremiereLocation.YOUTUBE)
        assert session.effective_premiere_location == PremiereLocation.YOUTUBE
        session.premiere_location = PremiereLocation.DISCORD
        assert session.effective_premiere_location == PremiereLocation.DISCORD


@pytest.mark.django_db
class TestSessionTransitions:
    def test_happy_path_content_session(self, conference):
        session = make_session(conference, kind=SessionKind.WORKSHOP)
        link = add_presenter(session, make_presenter(conference))
        session.mark_invited()
        assert session.status == SessionStatus.INVITED
        link.confirm()
        assert link.is_confirmed is True
        session.confirm()
        assert session.status == SessionStatus.CONFIRMED
        make_slot(session)
        session.schedule()
        assert session.status == SessionStatus.SCHEDULED
        session.publish()
        session.refresh_from_db()
        assert session.status == SessionStatus.PUBLISHED
        assert session.is_public is True

    def test_confirms_with_presenter_confirmed_up_front(self, conference):
        session = make_session(conference, kind=SessionKind.TALK)
        add_presenter(session, make_presenter(conference), confirmed=True)
        session.confirm()
        assert session.status == SessionStatus.CONFIRMED

    def test_program_item_confirms_with_no_presenters(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        assert session.status == SessionStatus.CONFIRMED

    def test_confirm_rejects_content_session_without_confirmed_presenter(
        self, conference
    ):
        session = make_session(conference, kind=SessionKind.PANEL)
        add_presenter(session, make_presenter(conference), role=PresenterRole.PANELIST)
        with pytest.raises(TransitionError, match="confirmed presenter"):
            session.confirm()
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT

    def test_confirm_rejects_wrong_status(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.cancel()
        with pytest.raises(TransitionError, match="from status Cancelled"):
            session.confirm()

    def test_mark_invited_rejects_confirmed(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        with pytest.raises(TransitionError):
            session.mark_invited()

    def test_schedule_rejects_without_slot(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        with pytest.raises(TransitionError, match="slot"):
            session.schedule()

    def test_schedule_rejects_draft(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        make_slot(session)
        with pytest.raises(TransitionError, match="from status Draft"):
            session.schedule()

    def test_publish_rejects_unscheduled(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        with pytest.raises(TransitionError, match="from status Confirmed"):
            session.publish()
        assert session.is_public is False

    def test_publish_rejects_when_slot_removed(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        slot = make_slot(session)
        session.schedule()
        slot.delete()
        with pytest.raises(TransitionError, match="slot"):
            session.publish()

    def test_cancel_unpublishes(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm()
        make_slot(session)
        session.schedule()
        session.publish()
        session.cancel()
        session.refresh_from_db()
        assert session.status == SessionStatus.CANCELLED
        assert session.is_public is False

    def test_transition_without_save(self, conference):
        session = make_session(conference, kind=SessionKind.BREAK)
        session.confirm(save=False)
        assert session.status == SessionStatus.CONFIRMED
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT


@pytest.mark.django_db
class TestPresenter:
    def test_str_slug_and_email_normalised(self, conference):
        presenter = make_presenter(
            conference, display_name="Ada Lovelace", email="  Ada@Example.COM "
        )
        assert str(presenter) == "Ada Lovelace"
        assert presenter.slug == "ada-lovelace"
        assert presenter.email == "ada@example.com"

    def test_slug_unique_per_edition(self, conference):
        make_presenter(conference, display_name="Ada")
        assert make_presenter(conference, display_name="Ada").slug == "ada-2"

    def test_can_exist_without_user_and_be_listed(self, conference):
        presenter = make_presenter(conference)
        assert presenter.user is None
        assert list(Presenter.objects.filter(user__isnull=True)) == [presenter]

    def test_timezone_validation(self, conference):
        presenter = make_presenter(conference, timezone="Africa/Lagos")
        presenter.full_clean()
        assert presenter.tzinfo.key == "Africa/Lagos"
        with pytest.raises(ValidationError, match="not a known IANA timezone"):
            validate_timezone("Mars/Olympus_Mons")


@pytest.mark.django_db
class TestSessionPresenter:
    def test_str_and_ordering(self, conference):
        session = make_session(conference, title="Panel")
        second = add_presenter(
            session, make_presenter(conference, display_name="B"), order=2
        )
        first = add_presenter(
            session,
            make_presenter(conference, display_name="A"),
            order=1,
            role=PresenterRole.MODERATOR,
        )
        assert list(session.session_presenters.all()) == [first, second]
        assert str(first) == "A (Moderator) on Panel"
        assert list(session.presenters.all()) == [first.presenter, second.presenter]

    def test_confirm_records_time(self, conference):
        link = add_presenter(make_session(conference), make_presenter(conference))
        assert link.is_confirmed is False
        link.confirm()
        link.refresh_from_db()
        assert link.confirmed_at is not None


@pytest.mark.django_db
class TestScheduleSlotShell:
    def test_end_defaults_from_duration(self, conference):
        session = make_session(conference, kind=SessionKind.WORKSHOP)
        slot = make_slot(session)
        assert slot.end_utc == slot.start_utc + timedelta(minutes=90)
        assert str(slot) == f"{session} at 2026-12-05 14:00 UTC"
        assert session.has_slot is True
        assert session.slot == slot

    def test_explicit_end_kept(self, conference):
        session = make_session(conference)
        slot = make_slot(session)
        end = slot.start_utc + timedelta(minutes=10)
        slot.end_utc = end
        slot.save()
        assert ScheduleSlot.objects.get(pk=slot.pk).end_utc == end

    def test_channel_str(self, conference):
        assert str(make_channel(conference, name="stage-1")) == "stage-1"


@pytest.mark.django_db
class TestActivityLog:
    def test_record_with_target_and_actor(self, conference, portal_user):
        session = make_session(conference, title="Talk")
        entry = ActivityLog.record(
            conference,
            "session.confirmed",
            target=session,
            actor=portal_user,
            message="Confirmed by hand",
            previous="DRAFT",
        )
        assert entry.target == session
        assert entry.data == {"previous": "DRAFT"}
        assert str(entry) == "testuser: session.confirmed"
        assert list(ActivityLog.for_target(session)) == [entry]
        assert list(conference.speaker_activity.all()) == [entry]

    def test_automatic_entry_has_no_actor(self, conference):
        entry = ActivityLog.record(conference, "pretix.order_paid")
        assert entry.actor is None
        assert entry.target is None
        assert str(entry) == "portal: pretix.order_paid"

    def test_newest_first(self, conference):
        session = make_session(conference)
        first = ActivityLog.record(conference, "a", target=session)
        second = ActivityLog.record(conference, "b", target=session)
        assert list(ActivityLog.for_target(session)) == [second, first]
