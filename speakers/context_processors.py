from portal.models import Conference

from .models import Presenter, speaker_module_enabled
from .permissions import (
    is_speaker_assignee,
    is_speaker_liaison,
    is_speaker_organizer,
)


def speaker_module(request):
    """Flags the shared rails need to show the speaker portal entries.

    * ``speaker_module_enabled``: the active edition has opted in.
    * ``is_speaker_liaison``: this user looks after at least one presenter, so
      the personal rail offers their sessions even though they are not an
      organizer.
    * ``is_speaker_assignee``: this user carries an organizer checklist
      item, so the personal rail offers the queue the digest links to.
    * ``is_speaker_presenter``: this user is a presenter in the active
      edition, so the navbar offers "Speaking".
    """
    # Three queries per authenticated render for an organizer, five for a
    # volunteer: the liaison and assignee lookups are skipped for organizers,
    # who already see everything. Left uncached on purpose while it is this
    # small; the moment another flag joins them, cache the result on the
    # request rather than adding a sixth query to every page.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "speaker_module_enabled": False,
            "is_speaker_liaison": False,
            "is_speaker_assignee": False,
            "is_speaker_presenter": False,
        }
    conference = Conference.get_active()
    enabled = speaker_module_enabled(conference)
    return {
        "speaker_module_enabled": enabled,
        "is_speaker_liaison": enabled
        and not is_speaker_organizer(user)
        and is_speaker_liaison(user, conference),
        "is_speaker_assignee": enabled
        and not is_speaker_organizer(user)
        and is_speaker_assignee(user, conference),
        "is_speaker_presenter": enabled
        and Presenter.objects.filter(conference=conference, user=user).exists(),
    }
