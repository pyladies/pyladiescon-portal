from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .mixins import SpeakerModuleRequiredMixin


class SpeakerPortalIndexView(
    LoginRequiredMixin, SpeakerModuleRequiredMixin, TemplateView
):
    """Placeholder landing page proving the feature flag is wired.

    Stage 1 replaces this with the organizer sessions list and the speaker
    dashboard.
    """

    template_name = "speakers/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context
