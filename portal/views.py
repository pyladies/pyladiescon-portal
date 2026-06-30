from django.contrib import messages
from django.contrib.auth import get_user
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView
from django.views.generic.edit import DeleteView, FormView, UpdateView

from common.mixins import AdminRequiredMixin, SuperuserRequiredMixin
from portal.common import (
    SPONSOR_AWAITING_INVOICE_STATUS,
    get_historical_comparison_data,
    get_stats_cached_values,
)
from portal.constants import (
    CACHE_KEY_ATTENDEE_COUNT,
    CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT,
    CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_DONATIONS_TOTAL_AMOUNT,
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
    SPONSORSHIP_GOAL,
)
from portal.forms import ConferenceForm, StartNewYearForm
from portal.models import Conference
from portal.services import (
    bring_forward_volunteers,
    clone_sponsorship_tiers,
    clone_teams,
)
from portal_account.models import PortalProfile
from sponsorship.models import SponsorshipProfile
from volunteer.models import Team, VolunteerProfile


def index(request):
    """
    Show personalized dashboard if user is authenticated and has a profile.
    Redirect to profile creation page if user is authenticated but has not completed their profile.
    Show landing page if user is not authenticated.
    """
    context = {}

    user = get_user(request)
    if user.is_authenticated:
        if not PortalProfile.objects.filter(user=user).exists():
            return redirect("portal_account:portal_profile_new")
        # Organizers land on their command center, not the volunteer landing.
        if user.is_superuser or user.is_staff:
            return redirect("organizer_dashboard")
        volunteer_profile = VolunteerProfile.objects.filter(
            user=user, conference=Conference.get_active()
        ).first()
        context["volunteer_profile"] = volunteer_profile
        context["roles"] = volunteer_profile.roles.all() if volunteer_profile else []
    else:
        context["volunteer_profile"] = None
        context["roles"] = []

    context["stats"] = get_stats_cached_values()
    context["can_start_next_year"] = Conference.can_start_next_year()

    return render(request, "portal/index.html", context)


def _stats_conference(request):
    """Resolve the conference to show stats for from ``?year=``.

    Falls back to the active conference when no (valid) year is given.
    """
    year = request.GET.get("year")
    if year:
        conference = Conference.objects.filter(year=year).first()
        if conference is not None:
            return conference
    return Conference.get_active()


def stats(request):
    """
    Show Interesting Public Stats
    """
    conference = _stats_conference(request)
    context = {
        "stats": get_stats_cached_values(conference),
        "conferences": Conference.objects.all(),
        "selected_conference": conference,
        # Years that predate the portal have no live data, only a snapshot.
        "historical_snapshot": conference.historical_snapshot if conference else None,
    }

    return render(request, "portal/stats.html", context)


def stats_json(request):
    """
    Return the stats as a JSON response
    """
    context = {}

    context["stats"] = get_stats_cached_values(_stats_conference(request))

    return JsonResponse(context)


def stats_comparison(request):
    """
    Show year-over-year comparison charts across all conference editions.
    """
    context = {"historical_comparison": get_historical_comparison_data()}

    return render(request, "portal/stats_comparison.html", context)


def dashboard_gallery(request):
    """
    Show a gallery of dashboards.
    """
    context = {}

    return render(request, "portal/dashboard_gallery.html", context)


class OrganizerDashboardView(AdminRequiredMixin, TemplateView):
    """Cross-app command center for organizers (superuser/staff).

    A router, not a reimplementation: the top row reuses the same cached stats
    as the public Stats page, and every action/attention item links to the
    existing list views. Nothing here duplicates those surfaces.
    """

    template_name = "portal/organizer_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conference = Conference.get_active()
        # Stats helpers assume an edition; with none active, fall back to empties
        # so the dashboard renders zeros instead of erroring.
        stats = get_stats_cached_values(conference) if conference else {}
        context["conference"] = conference
        context["can_start_next_year"] = Conference.can_start_next_year()

        # Top-line cross-app numbers (clean keys for the template).
        context["onboarded_count"] = stats.get(CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT, 0)
        # Goal percentages are raw divisions (can be long decimals and exceed
        # 100% once the goal is beaten). Round for display; cap the bar at 100%.
        sponsorship_percent = stats.get(CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT, 0)
        donation_percent = stats.get(CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT, 0)
        context["sponsorship_goal_percent"] = round(sponsorship_percent)
        context["sponsorship_bar_width"] = min(round(sponsorship_percent), 100)
        context["sponsorship_committed"] = stats.get(CACHE_KEY_SPONSORSHIP_COMMITTED, 0)
        context["sponsorship_goal"] = stats.get(SPONSORSHIP_GOAL, 0)
        context["donation_goal_percent"] = round(donation_percent)
        context["donation_bar_width"] = min(round(donation_percent), 100)
        context["donations_total"] = stats.get(CACHE_KEY_DONATIONS_TOTAL_AMOUNT, 0)
        context["donation_goal"] = conference.donation_goal if conference else 0
        context["attendee_count"] = stats.get(CACHE_KEY_ATTENDEE_COUNT, 0)
        context["attendee_first_time_count"] = stats.get(
            CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT, 0
        )

        # Needs-attention queue - all derivable, no new model fields.
        if conference:
            teams = Team.objects.filter(conference=conference)
            context["pending_reviews"] = sum(t.pending_members.count() for t in teams)
            context["unled_teams"] = sum(1 for t in teams if not t.team_leads.exists())
            context["awaiting_invoice"] = SponsorshipProfile.objects.filter(
                conference=conference,
                progress_status__in=SPONSOR_AWAITING_INVOICE_STATUS,
            ).count()
        else:
            context["pending_reviews"] = 0
            context["unled_teams"] = 0
            context["awaiting_invoice"] = 0
        return context


class StartNewYearView(SuperuserRequiredMixin, FormView):
    """Guided flow for organizers to stand up the next conference edition.

    Creates the edition and, in one step, carries selected data over from the
    previous edition (teams, sponsorship tiers, goal amounts, returning
    volunteers) and optionally activates it.
    """

    template_name = "portal/start_new_year.html"
    form_class = StartNewYearForm
    success_url = reverse_lazy("index")

    def dispatch(self, request, *args, **kwargs):
        if not Conference.can_start_next_year():
            messages.info(
                request,
                "Next year's conference can be started once the current "
                "edition's date has passed.",
            )
            return redirect("index")
        return super().dispatch(request, *args, **kwargs)

    def _previous_edition(self):
        return Conference.objects.order_by("-year").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["source"] = self._previous_edition()
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        source = self._previous_edition()

        conference = Conference(year=data["year"], name=data["name"], slug=data["slug"])
        conference.start_date = data.get("start_date")
        conference.end_date = data.get("end_date")
        conference.conference_date = data.get("conference_date")
        conference.pretix_event_slug = data.get("pretix_event_slug") or ""
        if source and data["copy_goals"]:
            conference.sponsorship_goal = source.sponsorship_goal
            conference.donation_goal = source.donation_goal
        if data["activate"]:
            conference.is_active = True
        conference.save()

        carried = []
        if source:
            if data["clone_teams"]:
                carried.append(f"{clone_teams(conference, source)} team(s)")
            if data["copy_tiers"]:
                carried.append(f"{clone_sponsorship_tiers(conference, source)} tier(s)")
            if data["bring_volunteers"]:
                carried.append(
                    f"{bring_forward_volunteers(conference, source)} volunteer(s)"
                )

        message = f"Created {conference}."
        if carried:
            message += f" Carried over: {', '.join(carried)}."
        if data["activate"]:
            message += " It is now the active edition."
        messages.success(self.request, message)
        return super().form_valid(form)


class ConferenceList(SuperuserRequiredMixin, ListView):
    model = Conference
    template_name = "portal/conference_list.html"
    context_object_name = "conferences"


class ConferenceUpdate(SuperuserRequiredMixin, UpdateView):
    model = Conference
    form_class = ConferenceForm
    template_name = "portal/conference_form.html"
    success_url = reverse_lazy("conference_list")


class ConferenceDelete(SuperuserRequiredMixin, DeleteView):
    model = Conference
    template_name = "portal/conference_confirm_delete.html"
    context_object_name = "conference"
    success_url = reverse_lazy("conference_list")

    def form_valid(self, form):
        # An edition referenced by teams/profiles/sponsors/tiers/donations is
        # PROTECTed; surface a clear message instead of a 500.
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"Cannot delete {self.object}: it still has teams, volunteers, "
                "sponsors, tiers, or donations. Remove those first.",
            )
            return redirect("conference_list")
