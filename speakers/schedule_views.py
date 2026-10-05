"""The schedule editor (design §10, task 4.2).

One page, one mutation endpoint. Every grid change, dragged or typed,
goes through ``SlotView``: PATCH upserts the session's slot and DELETE
removes it, both answering JSON so the page can show a refusal where it
happened. The board (the grid and the unscheduled sidebar together)
re-renders as one partial after each change, so a placed session leaves
the sidebar and any open popover goes with it.
"""

import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .constants import OFF_SCHEDULE_STATUSES, SessionStatus
from .forms import ProgramItemForm
from .mixins import SpeakerOrganizerRequiredMixin
from .models import ActivityLog, Room, ScheduleSlot, Session
from .schedule import (
    ROWS_PER_DAY,
    STEP_MINUTES,
    also_in,
    day_bounds,
    grid_for_day,
    publish_schedule,
    schedule_changes,
    schedule_days,
    timezone_options,
    unscheduled_sessions,
)

MAX_SLOT_MINUTES = ROWS_PER_DAY * STEP_MINUTES


class SlotError(Exception):
    """A slot mutation the endpoint refuses; the message goes to the page."""


def _resolve_room(conference, value):
    """A room of this edition, or None for the all-rooms lane.

    Strict on purpose, and shared by both write paths: a stale or
    mangled pk is a refusal with a reason, never a silent fall-back to
    the all-rooms band (which would block every room) and never a 500.
    """
    if value in (None, ""):
        return None
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise SlotError("That room does not exist in this edition.")
    room = Room.objects.filter(conference=conference, pk=pk, is_active=True).first()
    if room is None:
        raise SlotError("That room does not exist in this edition.")
    return room


def _parse_day(value, days):
    """The day tab to show: a valid ``?day=`` or the first tab."""
    if value:
        try:
            day = date.fromisoformat(value)
        except ValueError:
            return days[0]
        if day in days:
            return day
    return days[0]


def _parse_moment(value, field):
    """An aware UTC datetime from an ISO string; naive means UTC."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise SlotError(f"{field} is not a time the grid understands.")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt_timezone.utc)
    return moment.astimezone(dt_timezone.utc)


class ScheduleEditorView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView
):
    """The grid, the unscheduled sidebar, and the inline program-item form."""

    template_name = "speakers/schedule_editor.html"

    def get_template_names(self):
        if self.request.GET.get("board"):
            return ["speakers/_schedule_board.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = schedule_days(self.conference)
        day = _parse_day(self.request.GET.get("day"), days)
        full_day = bool(self.request.GET.get("full"))
        context.update(grid_for_day(self.conference, day, full_day=full_day))
        context.update(
            {
                "conference": self.conference,
                "rail_active": "schedule",
                "days": days,
                "day": day,
                "full_day": full_day,
                "unscheduled": unscheduled_sessions(self.conference),
                "timezones": timezone_options(self.conference),
                "unpublished": (
                    counts := {
                        kind: len(rows)
                        for kind, rows in schedule_changes(self.conference).items()
                    }
                ),
                "unpublished_total": sum(counts.values()),
                "step_minutes": STEP_MINUTES,
                "program_item_form": kwargs.get("program_item_form")
                or ProgramItemForm(conference=self.conference),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        """ "+ program item": born CONFIRMED, from the sidebar or a cell.

        The cell panel sends ``start`` and ``room`` along, so the item
        lands right where the organizer clicked; a refused window keeps
        the item, unscheduled, and says why.
        """
        form = ProgramItemForm(request.POST, conference=self.conference)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(program_item_form=form)
            )
        form.instance.status = SessionStatus.CONFIRMED
        with transaction.atomic():
            session = form.save()
            ActivityLog.record(
                self.conference,
                "session.created",
                target=session,
                actor=request.user,
                program_item=True,
            )
            placed = self.place(request, session)
        if placed is None:
            messages.success(
                request, f"Added “{session.title}”; drag it onto the grid."
            )
        day = _parse_day(self.request.GET.get("day"), schedule_days(self.conference))
        url = reverse("speakers:schedule_editor")
        return redirect(f"{url}?day={day:%Y-%m-%d}")

    def place(self, request, session):
        """Give the fresh program item the clicked cell's slot, if any.

        Returns the slot, or None when no ``start`` came along or the
        window was refused (the item stays, unscheduled, with the reason
        shown).
        """
        start = request.POST.get("start")
        if not start:
            return None
        slot = ScheduleSlot(session=session)
        try:
            slot.room = _resolve_room(self.conference, request.POST.get("room"))
            slot.start_utc = _parse_moment(start, "start")
            slot.save()
        except (SlotError, ValidationError) as error:
            reasons = (
                " ".join(error.messages)
                if isinstance(error, ValidationError)
                else str(error)
            )
            messages.warning(
                request,
                f"Added “{session.title}”, but could not place it: {reasons}",
            )
            return None
        ActivityLog.record(
            self.conference,
            "slot.placed",
            target=session,
            actor=request.user,
            start=slot.start_utc.isoformat(),
            end=slot.end_utc.isoformat(),
            room=slot.room.name if slot.room_id else "all rooms",
        )
        messages.success(
            request,
            f"Added “{session.title}” to the grid; speakers see it when the "
            "schedule is published.",
        )
        return slot


class ScheduleClearDayView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """POST: take every slot off the shown day in one go.

    A published session keeps its slot, since publishing requires one;
    the message says how many stayed behind.
    """

    def post(self, request):
        url = reverse("speakers:schedule_editor")
        try:
            day = date.fromisoformat(request.POST.get("day", ""))
        except ValueError:
            day = None
        if day is None or day not in schedule_days(self.conference):
            # A destructive endpoint refuses an unrecognised target
            # rather than picking another: the tabs may have changed
            # under this organizer since the page rendered.
            messages.warning(
                request,
                "That day is not on the schedule any more; nothing was " "unscheduled.",
            )
            return redirect(url)
        start, end = day_bounds(day)
        slots = ScheduleSlot.objects.filter(
            conference=self.conference, start_utc__lt=end, end_utc__gt=start
        ).select_related("session")
        cleared, kept = 0, 0
        with transaction.atomic():
            for slot in slots:
                session = slot.session
                if session.status == SessionStatus.PUBLISHED:
                    kept += 1
                    continue
                slot.delete()
                ActivityLog.record(
                    self.conference,
                    "slot.removed",
                    target=session,
                    actor=request.user,
                )
                cleared += 1
        label = day.strftime("%A %-d %B")
        messages.success(request, f"Took {cleared} session(s) off {label}.")
        if kept:
            messages.warning(
                request,
                f"{kept} published session(s) kept their slot; a published "
                "session needs one.",
            )
        return redirect(f"{url}?day={day:%Y-%m-%d}")


class SchedulePublishView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """POST: snapshot the grid for the speakers (design §10.1)."""

    def post(self, request):
        notify = bool(request.POST.get("notify"))
        result = publish_schedule(self.conference, request.user, notify=notify)
        if result["placed"] or result["moved"] or result["removed"]:
            told = (
                f" {result['told']} presenter(s) were emailed."
                if notify
                else " No emails were sent."
            )
            messages.success(
                request,
                "Schedule published: "
                f"{result['placed']} placed, {result['moved']} moved, "
                f"{result['removed']} taken off.{told}",
            )
        else:
            messages.info(request, "The published schedule already matches the grid.")
        day = _parse_day(request.GET.get("day"), schedule_days(self.conference))
        url = reverse("speakers:schedule_editor")
        return redirect(f"{url}?day={day:%Y-%m-%d}")


class SlotView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """The one mutation endpoint: PATCH places or moves, DELETE removes."""

    http_method_names = ["patch", "delete"]

    def get_session(self, slug):
        return get_object_or_404(
            Session.objects.for_conference(self.conference).select_related("kind"),
            slug=slug,
        )

    def patch(self, request, slug):
        session = self.get_session(slug)
        try:
            payload = self.read(request)
            with transaction.atomic():
                slot, created = self.apply(session, payload)
                ActivityLog.record(
                    self.conference,
                    "slot.placed" if created else "slot.moved",
                    target=session,
                    actor=request.user,
                    start=slot.start_utc.isoformat(),
                    end=slot.end_utc.isoformat(),
                    room=slot.room.name if slot.room_id else "all rooms",
                )
        except SlotError as error:
            return JsonResponse({"errors": [str(error)]}, status=400)
        except ValidationError as error:
            return JsonResponse({"errors": error.messages}, status=400)
        warnings = [
            also_in(link.presenter, link.session) for link in slot.presenter_clashes()
        ]
        return JsonResponse(
            {
                "ok": True,
                "session": session.slug,
                "status": session.status,
                "start": slot.start_utc.isoformat(),
                "end": slot.end_utc.isoformat(),
                "warnings": warnings,
            }
        )

    def delete(self, request, slug):
        session = self.get_session(slug)
        slot = ScheduleSlot.objects.filter(session=session).first()
        if slot is None:
            return JsonResponse({"errors": ["This session has no slot."]}, status=404)
        if session.status == SessionStatus.PUBLISHED:
            return JsonResponse(
                {
                    "errors": [
                        "A public session needs its slot; cancel the " "session first."
                    ]
                },
                status=400,
            )
        with transaction.atomic():
            slot.delete()
            ActivityLog.record(
                self.conference,
                "slot.removed",
                target=session,
                actor=request.user,
            )
        return JsonResponse({"ok": True, "session": session.slug})

    def read(self, request):
        """The JSON body, refused loudly when it is not an object."""
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise SlotError("The request body is not JSON.")
        if not isinstance(payload, dict):
            raise SlotError("The request body must be a JSON object.")
        return payload

    def apply(self, session, payload):
        """Upsert the session's slot from the payload and save it.

        ``room`` (a pk, or null for all rooms), ``start`` and either
        ``end`` or ``duration`` (minutes) are each optional: a drag sends
        room and start, a resize sends duration, the keyboard form sends
        everything. A move without an explicit end keeps the slot's length;
        a fresh slot without one gets the session's default duration.
        """
        if session.status in OFF_SCHEDULE_STATUSES:
            raise SlotError("This session is not on the program.")
        slot = ScheduleSlot.objects.filter(session=session).first()
        created = slot is None
        if created:
            slot = ScheduleSlot(session=session)
        length = None if created else slot.end_utc - slot.start_utc
        if "room" in payload:
            slot.room = _resolve_room(self.conference, payload["room"])
        if "start" in payload:
            slot.start_utc = _parse_moment(payload["start"], "start")
            slot.end_utc = slot.start_utc + length if length else None
        if slot.start_utc is None:
            raise SlotError("Give the slot a start time.")
        if "duration" in payload:
            try:
                minutes = int(payload["duration"])
            except (TypeError, ValueError):
                minutes = 0
            if not STEP_MINUTES <= minutes <= MAX_SLOT_MINUTES:
                raise SlotError(
                    f"A slot runs between {STEP_MINUTES} minutes and a day."
                )
            slot.end_utc = slot.start_utc + timedelta(minutes=minutes)
        elif "end" in payload:
            slot.end_utc = (
                _parse_moment(payload["end"], "end") if payload["end"] else None
            )
        if slot.end_utc is not None and slot.end_utc - slot.start_utc > timedelta(
            minutes=MAX_SLOT_MINUTES
        ):
            raise SlotError("A slot cannot run longer than a day.")
        slot.save()
        return slot, created
