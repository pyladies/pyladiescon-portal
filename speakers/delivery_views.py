"""Maintenance > Invitations: sent in the portal's eyes, not in its records."""

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from common.mixins import MaintainerRequiredMixin
from portal.models import Conference

from .delivery import (
    GRACE,
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
        items = unrecorded_invitations(conference) if conference else []
        context.update(
            {
                "conference": conference,
                "items": items,
                "sendable": sum(1 for item in items if not item.in_flight),
                "records_began": records_began(),
                "grace_minutes": int(GRACE.total_seconds() // 60),
                "history": retriggered_history(conference) if conference else [],
            }
        )
        return context


class MaintenanceInvitationsRetriggerView(MaintainerRequiredMixin, View):
    """Send again the ticked invitations, or every one that can be."""

    http_method_names = ["post"]

    def post(self, request):
        conference = Conference.get_active()
        if conference is None:
            messages.error(request, "There is no active edition.")
            return redirect("maintenance_invitations")
        ids = {int(pk) for pk in request.POST.getlist("invitation") if pk.isdigit()}
        everything = "all" in request.POST
        if not ids and not everything:
            messages.error(request, "Tick at least one invitation.")
            return redirect("maintenance_invitations")
        sent, skipped = retrigger(
            conference, ids, actor=request.user, everything=everything
        )
        if sent:
            messages.success(
                request,
                f"Sent {sent} invitation(s) again. Each row leaves this list "
                "once its email is recorded; if one is still here after a few "
                "minutes, look in the worker log for its invitation id.",
            )
        if skipped:
            messages.warning(
                request,
                f"Skipped {skipped}: recorded, answered or sent in the last "
                f"{int(GRACE.total_seconds() // 60)} minutes.",
            )
        return redirect("maintenance_invitations")
