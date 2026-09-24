from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import Http404

from portal.models import Conference

from .models import Presenter, speaker_module_enabled
from .permissions import can_work_queue, can_work_sessions, is_speaker_organizer


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


class SpeakerStaffRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Organizers and liaisons. Querysets still scope what a liaison sees."""

    def test_func(self):
        return can_work_sessions(self.request.user, self.conference)


class SpeakerQueueRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Organizers, liaisons, and volunteers carrying an organizer item.

    The digest mails an assignee a link to their queue, so the gate has to
    admit them; what they may then touch is narrowed per item.
    """

    def test_func(self):
        return can_work_queue(self.request.user, self.conference)


class SpeakerOrganizerRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Organizers only (creating sessions, inviting, publishing)."""

    def test_func(self):
        return is_speaker_organizer(self.request.user)


class PresenterRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """The speaker side: the user must be a presenter in the active edition.

    Sets ``self.presenter`` for the view; anyone without a presenter row
    gets 403 (the module is on, they are just not a speaker).
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        self.presenter = (
            Presenter.objects.filter(conference=self.conference, user=user)
            .select_related("liaison")
            .first()
        )
        # A proposer has a presenter row before anyone has said yes. The
        # speaker area belongs to people who are on the program, so being
        # a presenter is not enough: they need a session of the
        # conference's, which is what being onboarded means.
        return self.presenter is not None and self.presenter.is_onboarded
