"""The organizers' Publishing page (task 6.1, design §11.5).

One page for the three things that decide what the public sees: the
edition's master switch, which content sessions an organizer has
published, and the preview link the website build uses meanwhile.
"""

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from .constants import ProgramVisibility, SessionStatus
from .mixins import SpeakerOrganizerRequiredMixin
from .models import ActivityLog, Session, SpeakerSettings
from .public import preview_token, regenerate_preview

# Sessions in these statuses can be ticked: they are on the confirmed
# schedule. Not schedule.PUBLISHABLE_STATUSES, which is about the schedule.
TICKABLE = (SessionStatus.SCHEDULED, SessionStatus.PUBLISHED)


class ProgramPublishingView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView
):
    """GET shows the switches; POST changes one of them."""

    template_name = "speakers/program_publishing.html"

    def get_settings(self):
        return SpeakerSettings.objects.get(conference=self.conference)

    def content_sessions(self):
        """Content sessions somebody said yes to; only the ones on the
        published schedule can be ticked."""
        return (
            Session.objects.for_conference(self.conference)
            .filter(
                kind__is_content=True,
                status__in=(SessionStatus.CONFIRMED, *TICKABLE),
            )
            .select_related("kind", "published_slot", "published_slot__room")
            .order_by("published_slot__start_utc", "title")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = self.get_settings()
        published = settings.program_visibility == ProgramVisibility.PUBLISHED
        context.update(
            rail_active="publishing",
            settings=settings,
            program_published=published,
            sessions=[
                {"session": session, "can_publish": session.status in TICKABLE}
                for session in self.content_sessions()
            ],
            program_item_count=Session.objects.for_conference(self.conference)
            .filter(kind__is_content=False, published_slot__isnull=False)
            .exclude(status=SessionStatus.CANCELLED)
            .count(),
        )
        context["widget_snippets"] = self.widget_snippets()
        context["allowed_origins"] = settings.api_origins
        user = self.request.user
        # The admin is where the list is edited; offer it only to someone
        # who can open that page (superusers included).
        if user.is_staff and user.has_perm("speakers.change_speakersettings"):
            context["origins_admin_url"] = reverse(
                "admin:speakers_speakersettings_change", args=[settings.pk]
            )
        context["data_links"] = self.data_links()
        if not published:
            token = preview_token(settings)
            context["preview_token"] = token
            context["preview_feed_url"] = self.request.build_absolute_uri(
                reverse("speakers:schedule_feed") + f"?preview={token}"
            )
        return context

    def widget_snippets(self):
        """Ready-to-paste code for each whole-program widget view."""
        script = self.request.build_absolute_uri(
            f"{django_settings.STATIC_URL}widget/v1.js"
        )
        return [
            {
                "view": view,
                "label": label,
                "code": (
                    f'<div data-pyladiescon-widget="{view}" '
                    f'data-conference="{self.conference.slug}"></div>\n'
                    f'<script src="{script}" defer></script>'
                ),
            }
            for view, label in (
                ("schedule", "Schedule"),
                ("speakers", "Speakers"),
                ("sessions", "Sessions"),
            )
        ]

    def data_links(self):
        """The public endpoints, for anyone building their own page."""
        slug = self.conference.slug
        return [
            {
                "key": name,
                "label": label,
                "url": self.request.build_absolute_uri(
                    reverse(f"speakers_api:{name}", args=[slug])
                ),
            }
            for name, label in (
                ("sessions", "Sessions (JSON)"),
                ("presenters", "Speakers (JSON)"),
                ("schedule", "Schedule by day (JSON)"),
                ("schedule_ics", "Calendar feed (.ics)"),
            )
        ]

    def post(self, request):
        action = request.POST.get("action")
        settings = self.get_settings()
        if action == "visibility":
            value = request.POST.get("visibility")
            if value not in ProgramVisibility.values:
                return HttpResponseBadRequest("Unknown visibility.")
            if value != settings.program_visibility:
                settings.program_visibility = value
                settings.save(update_fields=["program_visibility"])
                ActivityLog.record(
                    self.conference,
                    "program.visibility",
                    actor=request.user,
                    visibility=value,
                )
            if value == ProgramVisibility.PUBLISHED:
                messages.success(request, "The program is public.")
            else:
                messages.success(
                    request,
                    "The program is internal again: the public program is "
                    "empty and the website shows it as coming soon.",
                )
        elif action == "sessions":
            self.apply_ticks(request, set(request.POST.getlist("publish")))
        elif action == "regenerate":
            regenerate_preview(settings)
            ActivityLog.record(
                self.conference, "program.preview_regenerated", actor=request.user
            )
            messages.success(
                request,
                "New preview link made. Every earlier link has stopped working.",
            )
        else:
            return HttpResponseBadRequest("Unknown action.")
        return redirect("speakers:program_publishing")

    def apply_ticks(self, request, ticked):
        """Publish what is ticked, unpublish what is not, among sessions on
        the published schedule; anything else on the form is ignored."""
        published = unpublished = 0
        with transaction.atomic():
            for session in self.content_sessions().filter(status__in=TICKABLE):
                wanted = session.slug in ticked
                if wanted and session.status == SessionStatus.SCHEDULED:
                    session.publish()
                    action = "session.published"
                    published += 1
                elif not wanted and session.status == SessionStatus.PUBLISHED:
                    session.unpublish()
                    action = "session.unpublished"
                    unpublished += 1
                else:
                    continue
                ActivityLog.record(
                    self.conference, action, target=session, actor=request.user
                )
        if published or unpublished:
            messages.success(
                request, f"{published} published, {unpublished} taken off."
            )
        else:
            messages.info(request, "Nothing changed.")
