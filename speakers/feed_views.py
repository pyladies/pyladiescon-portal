"""The calendar endpoints (task 4.4, design §11.3).

Public feeds carry public sessions only until the §11.5 visibility
rules arrive; a presenter's own feed rides a signed token, because a
calendar app cannot log in. Everything reads the published schedule.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.views import View

from .feeds import (
    presenter_from_token,
    presenter_rows,
    public_rows,
    render_calendar,
)
from .mixins import PresenterRequiredMixin, SpeakerModuleRequiredMixin
from .models import PublishedSlot


def calendar_response(text, filename=None):
    """text/calendar with the five-minute cache §11.3 asks for."""
    response = HttpResponse(text, content_type="text/calendar; charset=utf-8")
    response["Cache-Control"] = "max-age=300"
    if filename:
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ScheduleFeedView(SpeakerModuleRequiredMixin, View):
    """The whole public program, with the §11.3 filters."""

    def get(self, request):
        sessions = [slug for slug in request.GET.get("sessions", "").split(",") if slug]
        rows = public_rows(
            self.conference,
            sessions=sessions or None,
            kind=request.GET.get("kind") or None,
            room=request.GET.get("room") or None,
        )
        return calendar_response(
            render_calendar(f"{self.conference.name} schedule", rows)
        )


class SessionFeedView(SpeakerModuleRequiredMixin, View):
    """One public session, for a per-session subscription."""

    def get(self, request, slug):
        rows = list(public_rows(self.conference, sessions=[slug]))
        if not rows:
            raise Http404("Not on the public schedule.")
        return calendar_response(
            render_calendar(rows[0].session.title, rows),
            filename=f"{slug}.ics",
        )


class PresenterFeedView(SpeakerModuleRequiredMixin, View):
    """A presenter's personal feed: their sessions, public or not."""

    def get(self, request, token):
        presenter = presenter_from_token(token)
        if presenter is None or presenter.conference_id != self.conference.pk:
            raise Http404("No such feed.")
        rows = presenter_rows(self.conference, presenter)
        return calendar_response(
            render_calendar(f"{self.conference.name}: your sessions", rows)
        )


class MySessionFeedView(LoginRequiredMixin, PresenterRequiredMixin, View):
    """The add-to-calendar download on the speaker's own schedule page."""

    def get(self, request, slug):
        row = (
            PublishedSlot.objects.filter(
                conference=self.conference,
                session__slug=slug,
                session__session_presenters__presenter=self.presenter,
            )
            .select_related("session", "session__kind", "room", "conference")
            .first()
        )
        if row is None:
            raise Http404("Not on the published schedule.")
        return calendar_response(
            render_calendar(row.session.title, [row]),
            filename=f"{slug}.ics",
        )
