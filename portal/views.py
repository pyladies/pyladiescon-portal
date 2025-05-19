from django.shortcuts import redirect, render

from portal_account.models import PortalProfile
from volunteer.languages import LANGUAGES
from volunteer.models import Team, VolunteerProfile


def index(request):
    """
    Show personalized dashboard if user is authenticated and has a profile.
    Redirect to profile creation page if user is authenticated but has not completed their profile.
    Show landing page if user is not authenticated.
    """
    context = {}

    if (
        request.user
        and request.user.is_authenticated
        and not PortalProfile.objects.filter(user=request.user).exists()
    ):
        return redirect("portal_account:portal_profile_new")

    user = request.user
    volunteer_profile = VolunteerProfile.objects.filter(user=user).first()
    context["volunteer_profile"] = volunteer_profile

    lang_dict = dict(LANGUAGES)
    context["lang_dict"] = lang_dict

    teams = []
    if volunteer_profile:
        # Prefetch team_leads and team members (and their users) for all teams in one go
        teams_qs = volunteer_profile.teams.prefetch_related(
            "team_leads__user", "team__user"
        ).all()

        for team in teams_qs:
            leads = team.team_leads.all()
            members = team.team.all().exclude(pk=volunteer_profile.pk)
            teams.append(
                {
                    "name": team.short_name,
                    "leads": leads,
                    "members": members,
                }
            )
    context["teams"] = teams
    context["roles"] = volunteer_profile.roles.all() if volunteer_profile else []

    return render(request, "portal/index.html", context)
