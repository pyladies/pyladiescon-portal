"""The calendar endpoints (task 4.4, design §11.3).

Public feeds carry the public program (design §11.5, ``speakers.public``),
and accept the website's ``?preview=`` token, whose responses are never
cached; a presenter's own feed rides a signed token, because a
calendar app cannot log in. Everything reads the published schedule.
"""

from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.views import View

from .feeds import (
    presenter_from_token,
    presenter_rows,
    public_rows,
    render_calendar,
)
from .mixins import SpeakerModuleRequiredMixin


def calendar_response(text, private=False, preview=False):
    """text/calendar with the five-minute cache §11.3 asks for.

    Served inline on purpose: every one of these is a subscription
    target, and a downloaded copy is stale the moment a publish moves
    anything — which is why there is no download variant at all.
    """
    response = HttpResponse(text, content_type="text/calendar; charset=utf-8")
    if preview:
        # A preview shows the draft program; no cache may keep a copy.
        response["Cache-Control"] = "no-store"
    else:
        # A personal feed must not sit in a shared cache.
        response["Cache-Control"] = ("private, " if private else "") + "max-age=300"
    return response


class ScheduleFeedView(SpeakerModuleRequiredMixin, View):
    """The whole public program, with the §11.3 filters."""

    def get(self, request):
        sessions = [slug for slug in request.GET.get("sessions", "").split(",") if slug]
        room = request.GET.get("room") or None
        if room is not None:
            try:
                room = int(room)
            except ValueError:
                return HttpResponseBadRequest("Unknown room.")
        preview = request.GET.get("preview")
        rows = public_rows(
            self.conference,
            sessions=sessions or None,
            kind=request.GET.get("kind") or None,
            room=room,
            preview=preview,
        )
        return calendar_response(
            render_calendar(f"{self.conference.name} schedule", rows),
            preview="preview" in request.GET,
        )


class SessionFeedView(SpeakerModuleRequiredMixin, View):
    """One public session, for a per-session subscription."""

    def get(self, request, slug):
        preview = request.GET.get("preview")
        rows = list(public_rows(self.conference, sessions=[slug], preview=preview))
        if not rows:
            raise Http404("Not on the public schedule.")
        return calendar_response(
            render_calendar(rows[0].session.title, rows),
            preview="preview" in request.GET,
        )


class PresenterFeedView(SpeakerModuleRequiredMixin, View):
    """A presenter's personal feed: their sessions, public or not."""

    def get(self, request, token):
        presenter = presenter_from_token(token)
        if presenter is None or presenter.conference_id != self.conference.pk:
            raise Http404("No such feed.")
        sessions = [slug for slug in request.GET.get("sessions", "").split(",") if slug]
        rows = presenter_rows(self.conference, presenter, sessions=sessions or None)
        return calendar_response(
            render_calendar(f"{self.conference.name}: your sessions", rows),
            private=True,
        )
