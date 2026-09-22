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

#: Session keys: one remembers a settled agreement, the other counts how
#: many times the gate has turned this account away without one.
AGREED_KEY = "portal_account.agreed"
TRIES_KEY = "portal_account.agreement_tries"

#: How often an app's own page may be offered before the gate stops trusting
#: it and uses its own, which always collects the agreement. Low enough to
#: end a redirect loop in a blink, high enough that someone wandering the
#: site before agreeing never notices.
MAX_TRIES = 3

#: Prefixes the gate never redirects away from: signing in and out, email
#: confirmation, the Django admin, and the assets a page needs to render.
#: Every entry keeps its trailing slash, so a future app mounted at
#: /accounts-of-something/ is not exempt by accident.
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
            if request.session.get(AGREED_KEY) or has_agreed(user):
                # Agreement is permanent, so remember it and stop asking the
                # database on every page for the rest of the session.
                request.session[AGREED_KEY] = True
                request.session.pop(TRIES_KEY, None)
            else:
                target = self._target_for(request, user)
                if request.path != target:
                    return redirect(target)
        return self.get_response(request)

    def _target_for(self, request, user):
        """Where to send this request, without trapping anyone.

        An app can own a richer page (``ONBOARDING_URL_RESOLVERS``), but a
        page that does not actually collect the agreement would bounce the
        visitor straight back here, forever. So the gate counts how often it
        has turned this account away, and after a few goes uses its own page
        instead. The count is cleared the moment they agree.
        """
        target = agreement_url_for(user)
        if request.path == target:
            # Arriving at the page that asks is not being turned away.
            return target
        tries = request.session.get(TRIES_KEY, 0) + 1
        request.session[TRIES_KEY] = tries
        if tries > MAX_TRIES:
            return reverse("portal_account:agreements")
        return target

    def _exempt(self, request):
        path = request.path
        if path.startswith(EXEMPT_PREFIXES):
            return True
        for prefix in (settings.STATIC_URL, settings.MEDIA_URL):
            # STATIC_URL is stored without a leading slash in this project.
            if prefix and path.startswith("/" + prefix.lstrip("/")):
                return True
        return False
