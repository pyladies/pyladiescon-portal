from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .mixins import SpeakerModuleRequiredMixin
from .services import (
    InvitationError,
    accept_invitation,
    decline_invitation,
    resolve_invitation,
)


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


class InvitationView(SpeakerModuleRequiredMixin, View):
    """The page an invitation link opens: accept or decline.

    No login is needed: the signed token is the credential. Accepting links
    or creates the account and signs the presenter in, so the link doubles
    as their first magic-link login.
    """

    def get_invitation(self, request, token):
        try:
            return resolve_invitation(token, self.conference)
        except InvitationError as exc:
            return render(
                request,
                "speakers/invitation_invalid.html",
                {"reason": exc.reason, "conference": self.conference},
            )

    def get(self, request, token):
        invitation = self.get_invitation(request, token)
        if not hasattr(invitation, "presenter"):
            return invitation
        if invitation.opened_at is None:
            invitation.opened_at = timezone.now()
            invitation.save(update_fields=["opened_at", "modified_date"])
        return render(
            request,
            "speakers/invitation.html",
            {"invitation": invitation, "conference": self.conference},
        )

    def post(self, request, token):
        invitation = self.get_invitation(request, token)
        if not hasattr(invitation, "presenter"):
            return invitation
        if request.POST.get("action") == "decline":
            decline_invitation(invitation)
            return render(
                request,
                "speakers/invitation_declined.html",
                {"invitation": invitation, "conference": self.conference},
            )
        user = accept_invitation(invitation)
        if request.user.is_authenticated and request.user != user:
            logout(request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            f"Thanks for accepting, {invitation.presenter.display_name}. "
            "You're signed in.",
        )
        return redirect("speakers:index")
