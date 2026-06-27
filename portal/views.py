from django.contrib import messages
from django.contrib.auth import get_user
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from common.mixins import AdminRequiredMixin
from portal.common import get_historical_comparison_data, get_stats_cached_values
from portal.forms import StartNewYearForm
from portal.models import Conference
from portal.services import (
    bring_forward_volunteers,
    clone_sponsorship_tiers,
    clone_teams,
)
from portal_account.models import PortalProfile
from volunteer.models import VolunteerProfile


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


class StartNewYearView(AdminRequiredMixin, FormView):
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
