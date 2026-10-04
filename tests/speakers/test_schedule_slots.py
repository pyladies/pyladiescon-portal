"""The overlap rules on the schedule grid (task 4.1, design §8.5).

Two slots may not share a channel, and an all-channel band blocks the whole
grid, except that two program-kind bands may coexist. A presenter booked
twice at once is a warning, never an error.
"""

from datetime import datetime, timedelta, timezone

import pytest
from django.core.exceptions import ValidationError

from portal.models import Conference
from speakers.models import ScheduleSlot

from .factories import (
    add_presenter,
    make_channel,
    make_presenter,
    make_session,
    make_slot,
)

T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def other_conference(db):
    return Conference.objects.create(year=2024, name="PyLadiesCon 2024", slug="2024")


def place(session, minutes=0, length=None, **kwargs):
    """A slot ``minutes`` after two o'clock, ``length`` minutes long.

    Without ``length`` the end defaults from the session duration, as in
    production (a workshop runs 90 minutes, a break 15).
    """
    kwargs["start_utc"] = T0 + timedelta(minutes=minutes)
    if length is not None:
        kwargs["end_utc"] = kwargs["start_utc"] + timedelta(minutes=length)
    return make_slot(session, **kwargs)


@pytest.mark.django_db
class TestChannelOverlap:
    def test_two_slots_on_one_channel_may_not_overlap(self, conference):
        channel = make_channel(conference)
        place(make_session(conference, title="Shapely tables"), channel=channel)
        with pytest.raises(ValidationError) as excinfo:
            place(make_session(conference), minutes=60, channel=channel)
        assert "Shapely tables" in str(excinfo.value)
        assert "14:00 to 15:30 UTC" in str(excinfo.value)
        assert ScheduleSlot.objects.count() == 1

    def test_back_to_back_slots_are_fine(self, conference):
        channel = make_channel(conference)
        place(make_session(conference), channel=channel)
        place(make_session(conference), minutes=90, channel=channel)
        assert ScheduleSlot.objects.count() == 2

    def test_parallel_channels_are_fine(self, conference):
        place(make_session(conference), channel=make_channel(conference))
        place(make_session(conference), channel=make_channel(conference))
        assert ScheduleSlot.objects.count() == 2

    def test_moving_a_slot_does_not_collide_with_itself(self, conference):
        slot = place(make_session(conference), channel=make_channel(conference))
        slot.start_utc += timedelta(minutes=15)
        slot.end_utc += timedelta(minutes=15)
        slot.save()
        assert ScheduleSlot.objects.get(pk=slot.pk).start_utc == T0 + timedelta(
            minutes=15
        )

    def test_a_cancelled_session_frees_its_time(self, conference):
        channel = make_channel(conference)
        cancelled = make_session(conference)
        place(cancelled, channel=channel)
        cancelled.cancel()
        place(make_session(conference), channel=channel)
        assert ScheduleSlot.objects.count() == 2

    def test_another_edition_is_another_grid(self, conference, other_conference):
        place(make_session(conference))
        place(make_session(other_conference))
        assert ScheduleSlot.objects.count() == 2


@pytest.mark.django_db
class TestAllChannelBands:
    def test_a_band_blocks_a_channel_slot(self, conference):
        place(make_session(conference, kind="BREAK"))
        with pytest.raises(ValidationError):
            place(make_session(conference), length=10, channel=make_channel(conference))

    def test_a_channel_slot_blocks_a_band(self, conference):
        place(make_session(conference), channel=make_channel(conference))
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="BREAK"))

    def test_two_program_bands_may_share_the_window(self, conference):
        place(make_session(conference, kind="BREAK"), length=60)
        place(make_session(conference, kind="SOCIAL"), minutes=15)
        assert ScheduleSlot.objects.count() == 2

    def test_a_content_band_tolerates_no_company(self, conference):
        place(make_session(conference, kind="WORKSHOP"))
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="BREAK"), minutes=15)

    def test_a_program_band_still_collides_with_a_content_band(self, conference):
        place(make_session(conference, kind="BREAK"), length=60)
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="WORKSHOP"), minutes=15)


@pytest.mark.django_db
class TestWindow:
    def test_the_slot_must_end_after_it_starts(self, conference):
        with pytest.raises(ValidationError) as excinfo:
            place(make_session(conference), length=0)
        assert "end_utc" in excinfo.value.message_dict

    def test_the_rules_wait_for_the_fields(self, conference):
        assert ScheduleSlot().clean() is None
        slot = ScheduleSlot(session=make_session(conference))
        with pytest.raises(ValidationError) as excinfo:
            slot.full_clean()
        assert "start_utc" in excinfo.value.message_dict


@pytest.mark.django_db
class TestPresenterClashes:
    def test_a_double_booked_presenter_is_a_warning_not_a_block(self, conference):
        ada = make_presenter(conference, display_name="Ada")
        first = make_session(conference, title="First")
        second = make_session(conference, title="Second")
        add_presenter(first, ada)
        add_presenter(second, ada)
        place(first, channel=make_channel(conference))
        slot = place(second, minutes=30, channel=make_channel(conference))
        clashes = list(slot.presenter_clashes())
        assert [(link.presenter, link.session) for link in clashes] == [(ada, first)]
        assert [link.session for link in first.slot.presenter_clashes()] == [second]

    def test_no_overlap_means_no_warning(self, conference):
        ada = make_presenter(conference)
        first = make_session(conference)
        second = make_session(conference)
        add_presenter(first, ada)
        add_presenter(second, ada)
        place(first, channel=make_channel(conference))
        slot = place(second, minutes=90, channel=make_channel(conference))
        assert list(slot.presenter_clashes()) == []

    def test_someone_elses_booking_is_not_a_clash(self, conference):
        first = make_session(conference)
        second = make_session(conference)
        add_presenter(first, make_presenter(conference))
        add_presenter(second, make_presenter(conference))
        place(first, channel=make_channel(conference))
        slot = place(second, minutes=30, channel=make_channel(conference))
        assert list(slot.presenter_clashes()) == []
