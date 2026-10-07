"""The organizers' Publishing page (task 6.1, design §11.5), in three tabs.

- Publish: which content sessions are public (the program's master switch
  sits in the header every tab shares).
- Preview: the program through the website's own widget.
- Share: the widget code, the websites allowed to show it, the data feeds,
  and the preview token for whoever builds the website.
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
TABS = {
    "publish": "speakers:program_publishing",
    "preview": "speakers:program_preview",
    "share": "speakers:program_share",
}


class PublishingTabView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView
):
    """What every tab shares: the header with the master switch."""

    tab = None

    def get_settings(self):
        return SpeakerSettings.objects.get(conference=self.conference)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.settings_row = self.get_settings()
        context.update(
            rail_active="publishing",
            tab=self.tab,
            conference=self.conference,
            settings=self.settings_row,
            program_published=(
                self.settings_row.program_visibility == ProgramVisibility.PUBLISHED
            ),
        )
        return context


class ProgramPublishingView(PublishingTabView):
    """The Publish tab. POST takes every form on the three tabs and goes
    back to the tab it came from."""

    template_name = "speakers/program_publishing.html"
    tab = "publish"

    def content_sessions(self):
        """Content sessions somebody said yes to; only the ones on the
        confirmed schedule can be ticked."""
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
        context.update(
            sessions=[
                {"session": session, "can_publish": session.status in TICKABLE}
                for session in self.content_sessions()
            ],
            program_item_count=Session.objects.for_conference(self.conference)
            .filter(kind__is_content=False, published_slot__isnull=False)
            .exclude(status=SessionStatus.CANCELLED)
            .count(),
        )
        return context

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
                "New preview token made. Every earlier one has stopped working.",
            )
        else:
            return HttpResponseBadRequest("Unknown action.")
        return redirect(TABS.get(request.POST.get("next"), TABS["publish"]))

    def apply_ticks(self, request, ticked):
        """Publish what is ticked, unpublish what is not, among sessions on
        the confirmed schedule; anything else on the form is ignored."""
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


class ProgramPreviewView(PublishingTabView):
    """The Preview tab: the program through the website's own widget.

    While the program is internal: "draft" (the default) shows everything
    on the confirmed schedule, ticked or not, through the preview token;
    "public" shows what visitors get today. Once the program is public
    there is only the public view, since preview tokens stop working then.
    """

    template_name = "speakers/program_preview.html"
    tab = "preview"
    VIEWS = (
        ("schedule", "Schedule"),
        ("sessions", "Sessions"),
        ("speakers", "Speakers"),
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        draft = (
            not context["program_published"]
            and self.request.GET.get("show") != "public"
        )
        view = self.request.GET.get("view")
        if view not in dict(self.VIEWS):
            view = "schedule"
        context.update(
            draft=draft,
            view=view,
            views=self.VIEWS,
            preview_token=preview_token(self.settings_row) if draft else None,
        )
        return context


class ProgramShareView(PublishingTabView):
    """The Share tab: everything for putting the program on a website."""

    template_name = "speakers/program_share.html"
    tab = "share"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = self.settings_row
        context.update(
            widget_snippets=self.widget_snippets(),
            data_links=self.data_links(),
            allowed_origins=settings.api_origins,
        )
        user = self.request.user
        # The admin is where the list is edited; offer it only to someone
        # who can open that page (superusers included).
        if user.is_staff and user.has_perm("speakers.change_speakersettings"):
            context["origins_admin_url"] = reverse(
                "admin:speakers_speakersettings_change", args=[settings.pk]
            )
        if not context["program_published"]:
            context["preview_token"] = preview_token(settings)
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
