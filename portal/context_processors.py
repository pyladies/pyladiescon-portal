from volunteer.models import VolunteerProfile

from .models import Conference


def active_conference(request):
    """Expose the active conference to all templates as ``active_conference``."""
    return {"active_conference": Conference.get_active()}


def user_capabilities(request):
    """Expose permission flags to every template so the nav is consistent.

    The nav lives in ``portal/base.html`` and therefore renders on every page,
    but ``volunteer_profile`` is only set by the handful of views that bother
    to. Without this processor the sponsorship nav check silently collapses to
    superuser-only everywhere else. Computing the flags here fixes that and
    gives every template one vocabulary:

    * ``is_organizer``          — superuser or staff (matches AdminRequiredMixin)
    * ``can_manage_sponsorship``— same as organizer (create/edit/tiers/invoice)
    * ``can_view_sponsorship``  — organizer OR an approved volunteer (read-only)
    * ``active_volunteer_profile`` — this user's profile for the active edition
    * ``leads_any_team``        — true if they lead at least one team
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "is_organizer": False,
            "can_manage_sponsorship": False,
            "can_view_sponsorship": False,
            "active_volunteer_profile": None,
            "leads_any_team": False,
        }

    is_organizer = user.is_superuser or user.is_staff
    profile = VolunteerProfile.objects.filter(
        user=user, conference=Conference.get_active()
    ).first()
    is_approved = bool(profile and profile.is_approved)

    return {
        "is_organizer": is_organizer,
        "can_manage_sponsorship": is_organizer,
        "can_view_sponsorship": is_organizer or is_approved,
        "active_volunteer_profile": profile,
        "leads_any_team": bool(profile and profile.team_leads.exists()),
    }
