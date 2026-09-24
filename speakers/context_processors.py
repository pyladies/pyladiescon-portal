from portal.models import Conference

from .models import Presenter, speaker_module_enabled
from .permissions import can_work_queue, is_speaker_liaison, is_speaker_organizer


def speaker_module(request):
    """Flags the shared rails need to show the speaker portal entries.

    * ``speaker_module_enabled``: the active edition has opted in.
    * ``is_speaker_liaison``: this user looks after at least one presenter, so
      the personal rail offers their sessions even though they are not an
      organizer.
    * ``can_work_speaker_queue``: this user may open "My volunteering
      tasks" (an organizer, a liaison, or anyone carrying an organizer
      item), so the personal rail offers the page the digest links to.
    * ``is_speaker_presenter``: this user is a presenter in the active
      edition, so the navbar offers "Speaking".
    """
    # A handful of queries per authenticated render: the liaison lookup is
    # skipped for organizers, who already see everything, and the queue
    # predicate answers from the permission alone for them. Left uncached on
    # purpose while it is this small; the moment another flag joins them,
    # cache the result on the request rather than adding one more query to
    # every page.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "speaker_module_enabled": False,
            "is_speaker_liaison": False,
            "can_work_speaker_queue": False,
            "is_speaker_presenter": False,
        }
    conference = Conference.get_active()
    enabled = speaker_module_enabled(conference)
    return {
        "speaker_module_enabled": enabled,
        "is_speaker_liaison": enabled
        and not is_speaker_organizer(user)
        and is_speaker_liaison(user, conference),
        # Organizers included: the page is a person's own work, and it is
        # their rail entry too now that it has left the Organize rail.
        "can_work_speaker_queue": enabled and can_work_queue(user, conference),
        "is_speaker_presenter": enabled
        and Presenter.objects.filter(conference=conference, user=user).exists(),
    }
