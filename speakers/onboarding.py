"""Where a presenter finishes their account.

The portal-wide agreement gate (``portal_account.agreements``) asks each
resolver named in ``settings.ONBOARDING_URL_RESOLVERS`` where to send a user
who has not agreed yet. A presenter gets the speaker welcome page, which
collects the agreements along with a username and an optional password;
everyone else gets the plain agreements page.
"""

from django.urls import reverse

from portal.models import Conference

from .models import Presenter, speaker_module_enabled


def welcome_url_for(user):
    """The speaker welcome page when ``user`` is a presenter, else None."""
    conference = Conference.get_active()
    if not speaker_module_enabled(conference):
        return None
    if not Presenter.objects.filter(conference=conference, user=user).exists():
        return None
    return reverse("speakers:my_welcome")
