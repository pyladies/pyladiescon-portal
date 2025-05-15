from django.shortcuts import redirect
from django.urls import reverse


class TOSRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        excluded_path_prefixes = [
            "/admin/",
            "/accounts/",
            "/portal_account/profile/new",
            "/portal_account/profile/edit/",
            "/portal_account/profile/view/",
            "/volunteer/",
        ]

        current_path = request.path
        if any(current_path.startswith(prefix) for prefix in excluded_path_prefixes):
            return self.get_response(request)

        try:
            from portal_account.models import PortalProfile

            profile = PortalProfile.objects.get(user=request.user)

            if not profile.tos_agreement:
                profile_edit_url = profile.get_absolute_url()
                if current_path != profile_edit_url:
                    return redirect(profile_edit_url)
        except PortalProfile.DoesNotExist:
            return redirect("portal_account:portal_profile_new")

        return self.get_response(request)
