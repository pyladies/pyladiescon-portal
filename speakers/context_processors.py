from portal.models import Conference

from .models import speaker_module_enabled
from .permissions import is_speaker_liaison, is_speaker_organizer


def speaker_module(request):
    """Flags the shared rails need to show the speaker portal entries.

    * ``speaker_module_enabled``: the active edition has opted in.
    * ``is_speaker_liaison``: this user looks after at least one presenter, so
      the personal rail offers their sessions even though they are not an
      organizer.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"speaker_module_enabled": False, "is_speaker_liaison": False}
    conference = Conference.get_active()
    enabled = speaker_module_enabled(conference)
    return {
        "speaker_module_enabled": enabled,
        "is_speaker_liaison": enabled
        and not is_speaker_organizer(user)
        and is_speaker_liaison(user, conference),
    }
