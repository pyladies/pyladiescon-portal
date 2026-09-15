from django.http import Http404

from portal.models import Conference

from .models import speaker_module_enabled


class SpeakerModuleRequiredMixin:
    """Hide every speaker-portal view until the edition opts in.

    Raises 404 (not 403) when the flag is off for the active conference, so
    the module is invisible rather than merely locked while it is being
    built. ``self.conference`` is set for the view to scope its queries.
    """

    def dispatch(self, request, *args, **kwargs):
        self.conference = Conference.get_active()
        if not speaker_module_enabled(self.conference):
            raise Http404("The speaker portal is not enabled for this edition.")
        return super().dispatch(request, *args, **kwargs)
