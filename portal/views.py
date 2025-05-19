from django.shortcuts import redirect, render
from volunteer.models import VolunteerProfile, Team
from portal_account.models import PortalProfile
from volunteer.languages import LANGUAGES

def index(request):
    """Show personalized dashboard if user is authenticated and has a profile."""
    context = {}
    user = request.user
    if not user or not user.is_authenticated:
        return render(request, "portal/index.html", context)

    # Ensure portal profile exists
    if not PortalProfile.objects.filter(user=user).exists():
        return redirect("portal_account:portal_profile_new")

    # Volunteer profile (may not exist)
    volunteer_profile = VolunteerProfile.objects.filter(user=user).first()
    context["volunteer_profile"] = volunteer_profile

    # Language code to name mapping
    lang_dict = dict(LANGUAGES)
    context["lang_dict"] = lang_dict

    # Teams and team details
    teams = []
    if volunteer_profile:
        for team in volunteer_profile.teams.all():
            leads = team.team_leads.all()
            members = team.team.all().exclude(pk=volunteer_profile.pk)  # other members
            teams.append({
                "name": team.short_name,
                "leads": leads,
                "members": members,
            })
    context["teams"] = teams

    # Roles
    context["roles"] = volunteer_profile.roles.all() if volunteer_profile else []

    # Sponsorship status (placeholder)
    context["sponsorship_status"] = "Not a sponsor (feature coming soon)"

    return render(request, "portal/index.html", context)
