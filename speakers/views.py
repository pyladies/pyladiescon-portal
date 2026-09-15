from allauth.account.adapter import get_adapter as get_account_adapter
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView
from django.views.generic.edit import CreateView, UpdateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from .constants import SessionStatus
from .filters import PresenterFilter, SessionFilter
from .forms import (
    InviteForm,
    PresenterForm,
    ProgramItemForm,
    SessionForm,
    SessionPresenterForm,
)
from .mixins import (
    SpeakerModuleRequiredMixin,
    SpeakerOrganizerRequiredMixin,
    SpeakerStaffRequiredMixin,
)
from .models import ActivityLog, Invitation, Presenter, Session
from .permissions import can_work_sessions
from .services import (
    InvitationError,
    accept_invitation,
    cancel_invitation,
    decline_invitation,
    resolve_invitation,
    send_invitation,
)
from .tables import PresenterTable, SessionTable


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
        context["add_presenter_form"] = SessionPresenterForm(session=self.object)
        context["invite_form"] = InviteForm()
        latest = {}
        for invitation in Invitation.objects.filter(session=self.object).order_by(
            "creation_date", "id"
        ):
            latest[invitation.presenter_id] = invitation
        context["invitations_by_presenter"] = latest
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


class PresenterListView(
    LoginRequiredMixin, SpeakerStaffRequiredMixin, SingleTableMixin, FilterView
):
    """Every presenter in the edition, liaison-scoped."""

    model = Presenter
    table_class = PresenterTable
    filterset_class = PresenterFilter
    template_name = "speakers/presenter_list.html"
    paginate_by = 50

    def get_queryset(self):
        return (
            Presenter.objects.for_conference(self.conference)
            .visible_to(self.request.user)
            .with_listing_data()
            .order_by("display_name")
        )

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)
        kwargs["conference"] = self.conference
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "presenters"
        return context


class PresenterScopedMixin(LoginRequiredMixin, SpeakerStaffRequiredMixin):
    model = Presenter

    def get_queryset(self):
        return (
            Presenter.objects.for_conference(self.conference)
            .visible_to(self.request.user)
            .with_listing_data()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "presenters"
        return context


class PresenterDetailView(PresenterScopedMixin, DetailView):
    template_name = "speakers/presenter_detail.html"
    context_object_name = "presenter"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["session_links"] = self.object.session_links
        context["invitations"] = self.object.invitation_history
        context["activity"] = ActivityLog.for_target(self.object)[:20]
        return context


class PresenterUpdateView(PresenterScopedMixin, UpdateView):
    form_class = PresenterForm
    template_name = "speakers/presenter_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Saved {form.instance.display_name}.")
        return super().form_valid(form)


class PresenterCreateView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, CreateView
):
    model = Presenter
    form_class = PresenterForm
    template_name = "speakers/presenter_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        form.instance.conference = self.conference
        response = super().form_valid(form)
        ActivityLog.record(
            self.conference,
            "presenter.created",
            target=self.object,
            actor=self.request.user,
        )
        messages.success(self.request, f"Added {self.object.display_name}.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "presenters"
        return context


class OrganizerSessionActionMixin(LoginRequiredMixin, SpeakerOrganizerRequiredMixin):
    """POST-only actions on one session, organizer only."""

    def get_session(self):
        return get_object_or_404(
            Session.objects.for_conference(self.conference), pk=self.kwargs["pk"]
        )


class SessionAddPresenterView(OrganizerSessionActionMixin, View):
    def post(self, request, pk):
        session = self.get_session()
        form = SessionPresenterForm(request.POST, session=session)
        if form.is_valid():
            link = form.save()
            ActivityLog.record(
                self.conference,
                "session.presenter_added",
                target=session,
                actor=request.user,
                presenter_id=link.presenter_id,
                role=link.role,
            )
            messages.success(
                request,
                f"Added {link.presenter.display_name} as {link.get_role_display()}.",
            )
        else:
            messages.error(
                request,
                "Could not add the presenter: "
                + "; ".join(
                    f"{field}: {' '.join(errors)}"
                    for field, errors in form.errors.items()
                ),
            )
        return redirect(session.get_absolute_url())


class SessionRemovePresenterView(OrganizerSessionActionMixin, View):
    def post(self, request, pk, link_pk):
        session = self.get_session()
        link = get_object_or_404(session.session_presenters, pk=link_pk)
        name = link.presenter.display_name
        link.delete()
        ActivityLog.record(
            self.conference,
            "session.presenter_removed",
            target=session,
            actor=request.user,
            presenter_id=link.presenter_id,
        )
        messages.success(request, f"Removed {name} from the session.")
        return redirect(session.get_absolute_url())


class SessionInviteView(OrganizerSessionActionMixin, View):
    """Send (or resend) the invitation for one presenter on this session."""

    def post(self, request, pk, link_pk):
        session = self.get_session()
        link = get_object_or_404(
            session.session_presenters.select_related("presenter"), pk=link_pk
        )
        form = InviteForm(request.POST)
        form.is_valid()
        invitation = (
            Invitation.objects.filter(presenter=link.presenter, session=session)
            .exclude(accepted_at__isnull=False)
            .order_by("-creation_date", "-id")
            .first()
        )
        if invitation is None:
            invitation = Invitation(presenter=link.presenter, session=session)
        invitation.invited_by = request.user
        invitation.message_md = form.cleaned_data.get("message_md", "")
        send_invitation(invitation, actor=request.user)
        messages.success(request, f"Invitation sent to {link.presenter.email}.")
        return redirect(session.get_absolute_url())


class InvitationActionMixin(LoginRequiredMixin, SpeakerOrganizerRequiredMixin):
    def get_invitation(self):
        return get_object_or_404(
            Invitation.objects.filter(conference=self.conference).select_related(
                "presenter", "session"
            ),
            pk=self.kwargs["pk"],
        )


class InvitationResendView(InvitationActionMixin, View):
    def post(self, request, pk):
        invitation = self.get_invitation()
        try:
            send_invitation(invitation, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request, f"Invitation resent to {invitation.presenter.email}."
            )
        return redirect(invitation.presenter.get_absolute_url())


class InvitationCancelView(InvitationActionMixin, View):
    def post(self, request, pk):
        invitation = self.get_invitation()
        if invitation.is_open:
            cancel_invitation(invitation, actor=request.user)
            messages.success(request, "Invitation cancelled; its link no longer works.")
        else:
            messages.error(request, "Only an open invitation can be cancelled.")
        return redirect(invitation.presenter.get_absolute_url())
