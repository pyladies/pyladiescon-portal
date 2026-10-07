"""The public JSON API (task 6.2, design §11.1) and its calendar aliases.

Read-only, anonymous, per edition: ``/api/v1/<conference>/...``. Live
responses are cached for five minutes per edition (``speakers.api``,
dropped on every save that could change them); a response for a valid
``?preview=`` token is built fresh and never cached, and a junk token is
served from the cache like any other request. Browsers on the origins an
edition lists may read the responses cross-origin, preflight included.
"""

from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.utils.cache import patch_vary_headers
from django.views import View

from portal.models import Conference

from . import api
from .feed_views import ScheduleFeedView, SessionFeedView
from .models import speaker_module_enabled
from .public import preview_is_valid


class ApiConferenceMixin:
    """Resolve the edition from the URL instead of the active one."""

    def dispatch(self, request, *args, conference, **kwargs):
        self.conference = Conference.objects.filter(slug=conference).first()
        if self.conference is None or not speaker_module_enabled(self.conference):
            raise Http404("No such program.")
        return View.dispatch(self, request, *args, **kwargs)


class ApiView(ApiConferenceMixin, View):
    """GET only; subclasses build the payload."""

    http_method_names = ["get", "head", "options"]

    def build(self, request, preview):
        raise NotImplementedError  # pragma: no cover

    def get(self, request, **kwargs):
        self.kwargs = kwargs
        preview = request.GET.get("preview")
        previewing = preview_is_valid(self.conference, preview)
        # Only a valid token leaves the cache: a junk ?preview= would
        # otherwise let anyone force a full rebuild per hit, and blank a CDN.
        if previewing:
            response = JsonResponse(self.payload(request, preview, previewing))
            response["Cache-Control"] = "no-store"
        else:
            key = api.cache_key(self.conference, request)
            data = cache.get(key)
            if data is None:
                data = self.payload(request, None, False)
                cache.set(key, data, api.CACHE_SECONDS)
            response = JsonResponse(data)
            response["Cache-Control"] = f"public, max-age={api.CACHE_SECONDS}"
        return self.with_cors(request, response)

    def options(self, request, *args, **kwargs):
        """A browser's preflight, when the site sends a header that needs
        one: GET for a listed origin, the conditional headers a cache
        revalidation uses, remembered a day."""
        response = self.with_cors(request, super().options(request, *args, **kwargs))
        if response.has_header("Access-Control-Allow-Origin"):
            response["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            response["Access-Control-Allow-Headers"] = (
                "If-None-Match, If-Modified-Since"
            )
            response["Access-Control-Max-Age"] = "86400"
        return response

    def payload(self, request, preview, previewing):
        return {
            "conference": api.conference_block(self.conference),
            "program": api.program_state(self.conference, previewing),
            **self.build(request, preview if previewing else None),
        }

    def with_cors(self, request, response):
        patch_vary_headers(response, ["Origin"])
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and origin in self.conference.speaker_settings.api_origins:
            response["Access-Control-Allow-Origin"] = origin
        return response


class SessionsApiView(ApiView):
    def build(self, request, preview):
        sessions, public_ids = api.sessions_queryset(self.conference, preview)
        base = api.site_base()
        return {
            "sessions": [
                api.session_payload(self.conference, session, public_ids, base)
                for session in sessions
            ]
        }


class SessionApiView(ApiView):
    def build(self, request, preview):
        # While the program is internal every session answers the same
        # "coming soon" shape, so the widget never sees an error for it.
        if not preview and api.program_state(self.conference, False) == "internal":
            return {"session": None}
        sessions, public_ids = api.sessions_queryset(self.conference, preview)
        session = sessions.filter(slug=self.kwargs["slug"]).first()
        if session is None:
            raise Http404("Not on the public program.")
        return {
            "session": api.session_payload(
                self.conference, session, public_ids, api.site_base()
            )
        }


class PresentersApiView(ApiView):
    def build(self, request, preview):
        return {"presenters": api.presenters_data(self.conference, preview)}


class ScheduleApiView(ApiView):
    def build(self, request, preview):
        return api.schedule_data(self.conference, preview)


class ApiScheduleFeedView(ApiConferenceMixin, ScheduleFeedView):
    """``schedule.ics`` under the API's per-edition address (§11.3)."""


class ApiSessionFeedView(ApiConferenceMixin, SessionFeedView):
    """``sessions/<slug>.ics`` under the API's per-edition address."""
