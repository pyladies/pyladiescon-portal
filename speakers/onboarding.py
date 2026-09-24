"""Where a presenter finishes their account.

The portal-wide agreement gate (``portal_account.agreements``) asks each
resolver named in ``settings.ONBOARDING_URL_RESOLVERS`` where to send a user
who has not agreed yet. A presenter who is on the program gets the speaker
welcome page, which collects the agreements along with a username and an
optional password; everyone else, including someone waiting on an answer to
a proposal, gets the plain agreements page.
"""

from django.urls import reverse

from portal.models import Conference

from .models import Presenter, speaker_module_enabled


def welcome_url_for(user):
    """The speaker welcome page when ``user`` is a presenter, else None."""
    conference = Conference.get_active()
    if not speaker_module_enabled(conference):
        return None
    # On the program, not merely known to us: someone whose proposal has
    # not been answered has a presenter row and no speaker pages, so the
    # speaker welcome would 403 on them. They get the plain agreements
    # page, and the speaker welcome when their session is approved.
    on_the_program = Presenter.objects.filter(
        conference=conference,
        user=user,
        session_presenters__confirmed_at__isnull=False,
    ).exists()
    if not on_the_program:
        return None
    return reverse("speakers:my_welcome")
