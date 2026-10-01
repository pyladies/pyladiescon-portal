"""Maintenance > Invitations: sent in the portal's eyes, not in its records."""

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from common.mixins import MaintainerRequiredMixin
from portal.models import Conference

from .delivery import (
    GRACE,
    SENT,
    WAITING,
    records_began,
    retrigger,
    retriggered_history,
    unrecorded_invitations,
)


class MaintenanceInvitationsView(MaintainerRequiredMixin, TemplateView):
    """The active edition's invitations marked sent with no email record,
    with the sends already made from this page."""

    template_name = "speakers/maintenance_invitations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conference = Conference.get_active()
        context.update(
            {
                "conference": conference,
                "items": unrecorded_invitations(conference) if conference else [],
                "records_began": records_began(),
                "grace_minutes": int(GRACE.total_seconds() // 60),
                "history": retriggered_history(conference) if conference else [],
            }
        )
        return context


class MaintenanceInvitationsRetriggerView(MaintainerRequiredMixin, View):
    """Send one invitation again. One at a time on purpose: it emails a real
    person and ends the link they were last given."""

    http_method_names = ["post"]

    def post(self, request):
        conference = Conference.get_active()
        if conference is None:
            messages.error(request, "There is no active edition.")
            return redirect("maintenance_invitations")
        value = request.POST.get("invitation", "")
        if not value.isdigit():
            messages.error(request, "Choose an invitation to send again.")
            return redirect("maintenance_invitations")
        outcome, invitation = retrigger(conference, int(value), actor=request.user)
        if outcome == SENT:
            messages.success(
                request,
                f"Sent again to {invitation.presenter.display_name}. The row "
                "leaves this list once its email is recorded; if it is still "
                "here after a few minutes, look in the worker log for "
                f"invitation {invitation.pk}.",
            )
        elif outcome == WAITING:
            messages.warning(
                request,
                f"{invitation.presenter.display_name} was sent an email in the "
                f"last {int(GRACE.total_seconds() // 60)} minutes. Wait for it "
                "to be recorded before sending again.",
            )
        else:
            messages.warning(
                request,
                "That invitation is no longer on the list: its email was "
                "recorded, the presenter answered, or it was cancelled.",
            )
        return redirect("maintenance_invitations")
