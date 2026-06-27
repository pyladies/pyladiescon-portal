from django.contrib.auth import get_user
from django.http import JsonResponse
from django.shortcuts import redirect, render

from portal.common import get_historical_comparison_data, get_stats_cached_values
from portal.models import Conference
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
