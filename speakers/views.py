from allauth.account.adapter import get_adapter as get_account_adapter
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView
from django.views.generic.edit import CreateView, UpdateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from .constants import SessionStatus
from .filters import SessionFilter
from .forms import ProgramItemForm, SessionForm
from .mixins import (
    SpeakerModuleRequiredMixin,
    SpeakerOrganizerRequiredMixin,
    SpeakerStaffRequiredMixin,
)
from .models import ActivityLog, Session
from .permissions import can_work_sessions
from .services import (
    InvitationError,
    accept_invitation,
    decline_invitation,
    resolve_invitation,
)
from .tables import SessionTable


class SpeakerPortalIndexView(
    LoginRequiredMixin, SpeakerModuleRequiredMixin, TemplateView
):
    """Entry point: organizers and liaisons go to the sessions list.

    Everyone else sees a placeholder until the speaker dashboard (task 1.5)
    replaces it.
    """

    template_name = "speakers/index.html"

    def get(self, request, *args, **kwargs):
        if can_work_sessions(request.user, self.conference):
            return redirect("speakers:session_list")
        return super().get(request, *args, **kwargs)

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

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except InvitationError as exc:
            return render(
                request,
                "speakers/invitation_invalid.html",
                {"reason": exc.reason, "conference": self.conference},
            )

    def get(self, request, token):
        invitation = resolve_invitation(token, self.conference)
        if invitation.opened_at is None:
            invitation.opened_at = timezone.now()
            invitation.save(update_fields=["opened_at", "modified_date"])
        return render(
            request,
            "speakers/invitation.html",
            {"invitation": invitation, "conference": self.conference},
        )

    def post(self, request, token):
        invitation = resolve_invitation(token, self.conference)
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
        # Through allauth, so its signals and adapter hooks fire as on any
        # other sign-in.
        get_account_adapter(request).login(request, user)
        messages.success(
            request,
            f"Thanks for accepting, {invitation.presenter.display_name}. "
            "You're signed in.",
        )
        return redirect("speakers:index")


class SessionListView(
    LoginRequiredMixin, SpeakerStaffRequiredMixin, SingleTableMixin, FilterView
):
    """Every schedule row for the edition (design §3.1), liaison-scoped."""

    model = Session
    table_class = SessionTable
    filterset_class = SessionFilter
    template_name = "speakers/session_list.html"
    paginate_by = 50

    def get_queryset(self):
        return (
            Session.objects.for_conference(self.conference)
            .visible_to(self.request.user)
            .with_listing_data()
            .order_by("title")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context


class SessionScopedMixin(LoginRequiredMixin, SpeakerStaffRequiredMixin):
    """Detail/edit views over the sessions this user may see."""

    model = Session

    def get_queryset(self):
        return (
            Session.objects.for_conference(self.conference)
            .visible_to(self.request.user)
            .with_listing_data()
        )


class SessionDetailView(SessionScopedMixin, DetailView):
    template_name = "speakers/session_detail.html"
    context_object_name = "session"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["presenter_links"] = self.object.presenter_links
        context["activity"] = ActivityLog.for_target(self.object)[:20]
        return context


class SessionUpdateView(SessionScopedMixin, UpdateView):
    form_class = SessionForm
    template_name = "speakers/session_form.html"

    def form_valid(self, form):
        messages.success(self.request, f"Saved “{form.instance.title}”.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context


class SessionCreateView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, CreateView):
    model = Session
    form_class = SessionForm
    template_name = "speakers/session_form.html"

    def form_valid(self, form):
        form.instance.conference = self.conference
        response = super().form_valid(form)
        ActivityLog.record(
            self.conference,
            "session.created",
            target=self.object,
            actor=self.request.user,
        )
        messages.success(self.request, f"Created “{self.object.title}”.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context


class ProgramItemCreateView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, CreateView
):
    """ "+ program item": an opening, break or social, born CONFIRMED."""

    model = Session
    form_class = ProgramItemForm
    template_name = "speakers/program_item_form.html"

    def form_valid(self, form):
        form.instance.conference = self.conference
        form.instance.status = SessionStatus.CONFIRMED
        response = super().form_valid(form)
        ActivityLog.record(
            self.conference,
            "session.created",
            target=self.object,
            actor=self.request.user,
            program_item=True,
        )
        messages.success(self.request, f"Added “{self.object.title}” to the program.")
        return response

    def get_success_url(self):
        return reverse("speakers:session_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context
