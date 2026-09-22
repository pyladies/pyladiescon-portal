"""The Code of Conduct and Terms of Service gate.

Both agreements are recorded on ``PortalProfile``. Signup collects them, but
an account can arrive without ever meeting that form: a speaker invitation
creates one and signs the person in, and a sign-in code lets them back in
afterwards. This module is the single place that notices and asks.

The gate is a middleware rather than a mixin so it holds for every page,
including ones written later, and so a direct link into the portal cannot
walk past it.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.module_loading import import_string

from .models import PortalProfile

#: Prefixes the gate never redirects away from: signing in and out, email
#: confirmation, the Django admin, and the assets a page needs to render.
EXEMPT_PREFIXES = ("/accounts/", "/admin/", "/captcha/")


def has_agreed(user):
    """Whether this account has accepted both agreements.

    False for a signed-out visitor, so the helper is safe to call anywhere;
    the middleware checks that first and never gates one.
    """
    if not user.is_authenticated:
        return False
    return PortalProfile.objects.filter(
        user=user, coc_agreement=True, tos_agreement=True
    ).exists()


def agreement_url_for(user):
    """Where to send ``user`` to agree.

    Apps can own a richer page for their own people:
    ``settings.ONBOARDING_URL_RESOLVERS`` names callables taking the user and
    returning a URL or None. The speakers app uses it for the presenter
    welcome page, which asks for a username and an optional password as well.
    This module stays free of any knowledge of them.
    """
    for path in getattr(settings, "ONBOARDING_URL_RESOLVERS", ()):
        url = import_string(path)(user)
        if url:
            return url
    return reverse("portal_account:agreements")


class AgreementRequiredMiddleware:
    """Send a signed-in account that has not agreed to the page that asks.

    Anonymous visitors, exempt paths and the agreement page itself pass
    through. Non-GET requests are redirected too: a POST from a page they
    should not have reached is not one to honour.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not self._exempt(request):
            if not has_agreed(user):
                target = agreement_url_for(user)
                if request.path != target:
                    return redirect(target)
        return self.get_response(request)

    def _exempt(self, request):
        path = request.path
        if path.startswith(EXEMPT_PREFIXES):
            return True
        for prefix in (settings.STATIC_URL, settings.MEDIA_URL):
            # STATIC_URL is stored without a leading slash in this project.
            if prefix and path.startswith("/" + prefix.lstrip("/")):
                return True
        return False
