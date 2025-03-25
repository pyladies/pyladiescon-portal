from django.shortcuts import render, redirect


def index(request):
    """Redirect to profile creation page if user has not completed their profile."""
    context = {}
    from portal_account.models import PortalProfile

    if (
        request.user
        and request.user.is_authenticated
        and not PortalProfile.objects.filter(user=request.user).exists()
    ):
        return redirect("portal_account:portal_profile_new")
    return render(request, "portal/index.html", context)
