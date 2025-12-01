from django.contrib.auth import get_user
from django.http import JsonResponse
from django.shortcuts import redirect, render

from portal.common import get_stats_cached_values
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
        volunteer_profile = VolunteerProfile.objects.filter(user=user).first()
        context["volunteer_profile"] = volunteer_profile
        context["roles"] = volunteer_profile.roles.all() if volunteer_profile else []
    else:
        context["volunteer_profile"] = None
        context["roles"] = []

    context["stats"] = get_stats_cached_values()

    return render(request, "portal/index.html", context)


def stats(request):
    """
    Show Interesting Public Stats
    """
    context = {}

    context["stats"] = get_stats_cached_values()

    return render(request, "portal/stats.html", context)


def stats_json(request):
    """
    Return the stats as a JSON response
    """
    context = {}

    context["stats"] = get_stats_cached_values()

    return JsonResponse(context)
