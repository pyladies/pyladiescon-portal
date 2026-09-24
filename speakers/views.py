from allauth.account.adapter import get_adapter as get_account_adapter
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, FormView, UpdateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from attendee.models import PretixOrder
from common.tasks import enqueue
from portal_account import agreements
from volunteer.models import Team

from .board import build_board, write_board_csv
from .checklists import (
    ChecklistError,
    add_adhoc_item,
    apply_new_template_item,
    apply_template_item_changes,
    assign_item,
    complete_item,
    reopen_item,
    retire_template_item,
    skip_item,
    sync_template_order,
)
from .clock import today
from .constants import (
    DEFAULT_GUIDE_KEY,
    OPEN_ITEM_STATUSES,
    AssigneeDefault,
    AutoRule,
    ChecklistScope,
    ItemOwner,
    ItemStatus,
    ReadyOverride,
    SessionStatus,
)
from .emails import render_invitation_preview
from .filters import PresenterFilter, SessionFilter
from .forms import (
    DEFAULT_GUIDE_URL,
    AdhocItemForm,
    AssignItemForm,
    ChecklistTemplateForm,
    ChecklistTemplateItemForm,
    HandbookForm,
    InviteForm,
    NewHandbookForm,
    PresenterForm,
    PresenterInviteForm,
    PresenterRoleForm,
    ProgramItemForm,
    ReadinessGateForm,
    SessionForm,
    SessionPresenterForm,
    SessionPresenterRoleForm,
    SessionTypeForm,
    SpeakerOnboardingForm,
    SpeakerProfileForm,
    SpeakerSessionForm,
    SuggestCoPresenterForm,
    owner_choices,
)
from .lifecycle import waiting_on_labels
from .mixins import (
    PresenterRequiredMixin,
    SpeakerModuleRequiredMixin,
    SpeakerOrganizerRequiredMixin,
    SpeakerQueueRequiredMixin,
    SpeakerStaffRequiredMixin,
)
from .models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Handbook,
    HandbookReadReceipt,
    Invitation,
    Presenter,
    PresenterRole,
    ReadinessGate,
    Session,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)
from .permissions import (
    approved_teams,
    can_work_sessions,
    is_speaker_organizer,
    owned_by,
)
from .pretix import (
    PretixError,
    link_presenter_order,
    lookup_presenter_orders,
    unlink_presenter_order,
)
from .readiness import apply_readiness, refresh_for_conference, refresh_readiness
from .rules import evaluate_items
from .seeds import seed_checklists
from .services import (
    InvitationError,
    accept_invitation,
    cancel_invitation,
    change_presenter_role,
    decline_invitation,
    presenter_added_to_session,
    resolve_invitation,
    send_invitation,
)
from .tables import PresenterTable, SessionTable
from .tasks import send_copresenter_suggestion_task


class SpeakerPortalIndexView(
    LoginRequiredMixin, SpeakerModuleRequiredMixin, TemplateView
):
    """Entry point: presenters go to their dashboard, organizers and
    liaisons to the sessions list, anyone else to a short explanation."""

    template_name = "speakers/index.html"

    def get(self, request, *args, **kwargs):
        if Presenter.objects.filter(
            conference=self.conference, user=request.user
        ).exists():
            return redirect("speakers:my_dashboard")
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

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)
        kwargs["conference"] = self.conference
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context


def _identity_changes(form, fields):
    """Which of ``fields`` really changed, as ``{name: {"from", "to"}}``.

    Compares cleaned against initial rather than trusting ``changed_data``: a
    blank or omitted slug is cleaned back to the current address and is not
    a change."""
    return {
        name: {"from": form.initial.get(name), "to": form.cleaned_data[name]}
        for name in fields
        if name in form.changed_data
        and form.cleaned_data.get(name) != form.initial.get(name)
    }


def _note_identity_change(request, form, fields, action):
    """An organizer changed a title, name or address on a row whose identity
    is locked for the speaker: log old and new values, and warn that links
    already shared may break. Before the lock nothing is recorded here; the
    speaker-side views record their own changes."""
    changes = _identity_changes(form, fields)
    if not changes or not form.instance.identity_locked:
        return
    ActivityLog.record(
        form.instance.conference,
        action,
        target=form.instance,
        actor=request.user,
        changes=changes,
    )
    messages.warning(
        request,
        "Already scheduled: the "
        + " and ".join(form.fields[name].label.lower() for name in changes)
        + " changed, so links already shared may break.",
    )


class SessionScopedMixin(LoginRequiredMixin, SpeakerStaffRequiredMixin):
    """Detail/edit views over the sessions this user may see. Sessions are
    addressed by slug (unique per edition), never by number."""

    model = Session
    slug_field = "slug"
    slug_url_kwarg = "slug"

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
        context["waiting_on"] = waiting_on_labels(self.object)
        context["add_presenter_form"] = SessionPresenterForm(session=self.object)
        roles = list(
            self.object.kind.roles.filter(is_active=True).order_by("sort_order", "name")
        )
        context["role_forms"] = {
            link.pk: SessionPresenterRoleForm(
                instance=link,
                prefix=f"link{link.pk}",
                session=self.object,
                roles=roles,
            )
            for link in self.object.presenter_links
        }
        context["invite_form"] = InviteForm()
        latest = {}
        for invitation in Invitation.objects.filter(session=self.object).order_by(
            "creation_date", "id"
        ):
            latest[invitation.presenter_id] = invitation
        context["invitations_by_presenter"] = latest
        # The session's checklists: per presenter, plus session-scope items.
        items = list(
            self.object.checklist_items.select_related(
                "presenter", "assignee", "team", "completed_by", "session"
            ).order_by("presenter__display_name", "order", "id")
        )
        for item in items:
            item.overdue = item.is_overdue
        groups = []
        for link in self.object.presenter_links:
            mine = [i for i in items if i.presenter_id == link.presenter_id]
            if mine:
                groups.append(
                    {
                        "presenter": link.presenter,
                        "speaker": [i for i in mine if i.owner == ItemOwner.SPEAKER],
                        "organizer": [
                            i for i in mine if i.owner == ItemOwner.ORGANIZER
                        ],
                    }
                )
        context["checklist_groups"] = groups
        context["session_items"] = [i for i in items if i.presenter_id is None]
        # One query for the people and teams, shared by every row; each row
        # reads its own current value off the item (review of #425).
        context["owner_choices"] = owner_choices(self.conference)
        # A liaison reaches this page but may not hand work to someone else
        # (ItemAssignView is organizer-only), so do not offer them the select.
        context["can_assign"] = is_speaker_organizer(self.request.user)
        context["adhoc_form"] = AdhocItemForm(
            initial={"owner_kind": ItemOwner.ORGANIZER}, conference=self.conference
        )
        return context


class SessionUpdateView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, UpdateView):
    """Organizers only: liaisons read sessions but do not change them."""

    model = Session
    form_class = SessionForm
    template_name = "speakers/session_form.html"

    def get_queryset(self):
        return Session.objects.for_conference(self.conference)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        _note_identity_change(
            self.request, form, ("title", "slug"), "session.identity_changed"
        )
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

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
    slug_field = "slug"
    slug_url_kwarg = "slug"

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
        sent = [i for i in self.object.invitation_history if i.sent_at]
        context["latest_sent"] = max(sent, key=lambda i: i.sent_at) if sent else None
        context["accepted"] = next((i for i in sent if i.accepted_at), None)
        context["invite_form"] = PresenterInviteForm(presenter=self.object)
        items = list(
            self.object.checklist_items.select_related(
                "assignee", "team", "session", "completed_by"
            ).order_by("session__title", "order", "id")
        )
        for item in items:
            item.overdue = item.is_overdue
        context["speaker_items"] = [i for i in items if i.owner == ItemOwner.SPEAKER]
        context["organizer_items"] = [
            i for i in items if i.owner == ItemOwner.ORGANIZER
        ]
        # One query for the person-and-team options, shared by every row;
        # each row reads its own current value off the item.
        context["owner_choices"] = owner_choices(self.conference)
        context["adhoc_form"] = AdhocItemForm(conference=self.conference)
        context["can_assign"] = is_speaker_organizer(self.request.user)
        # Checklists only make sense once the presenter has been invited; ad-hoc
        # items added earlier still show.
        context["show_checklists"] = bool(context["latest_sent"] or items)
        settings_row = SpeakerSettings.objects.filter(
            conference=self.conference
        ).first()
        context["pretix_configured"] = bool(
            settings_row and settings_row.pretix_configured
        )
        context["matched_orders"] = list(
            PretixOrder.objects.filter(
                conference=self.conference, email__iexact=self.object.email
            ).order_by("-datetime")[:5]
        )
        return context


class PresenterUpdateView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, UpdateView
):
    """Organizers only. A liaison must not change the email an invitation
    goes to, nor hand the presenter to another liaison."""

    model = Presenter
    form_class = PresenterForm
    template_name = "speakers/presenter_form.html"

    def get_queryset(self):
        return Presenter.objects.for_conference(self.conference)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "presenters"
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        _note_identity_change(
            self.request,
            form,
            ("display_name", "slug"),
            "presenter.identity_changed",
        )
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
            Session.objects.for_conference(self.conference), slug=self.kwargs["slug"]
        )


class SessionAddPresenterView(OrganizerSessionActionMixin, View):
    def post(self, request, slug):
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
                role=link.role.code,
            )
            note = ""
            if presenter_added_to_session(link, actor=request.user):
                note = " They had already accepted, so they are confirmed on it."
            messages.success(
                request,
                f"Added {link.presenter.display_name} as {link.role.name}." + note,
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


class SessionEditPresenterView(OrganizerSessionActionMixin, View):
    """Change the role or the required flag; the checklist follows the role."""

    def post(self, request, slug, link_pk):
        session = self.get_session()
        link = get_object_or_404(
            session.session_presenters.select_related("presenter"), pk=link_pk
        )
        form = SessionPresenterRoleForm(
            request.POST, instance=link, prefix=f"link{link.pk}", session=session
        )
        if not form.is_valid():
            messages.error(request, "Could not change the role: pick a valid role.")
            return redirect(session.get_absolute_url())
        removed, created = change_presenter_role(
            link,
            form.cleaned_data["role"],
            is_required=form.cleaned_data["is_required"],
            actor=request.user,
        )
        note = f"{link.presenter.display_name} is now {link.role.name}."
        if removed or created:
            note += (
                f" Checklist updated: {removed} open item(s) dropped, {created} added."
            )
        messages.success(request, note)
        return redirect(session.get_absolute_url())


class SessionRemovePresenterView(OrganizerSessionActionMixin, View):
    def post(self, request, slug, link_pk):
        session = self.get_session()
        link = get_object_or_404(session.session_presenters, pk=link_pk)
        name, presenter_id = link.presenter.display_name, link.presenter_id
        with transaction.atomic():
            link.delete()
            # Their link must stop working: an open invitation to a session
            # they are no longer on would still accept.
            for invitation in Invitation.objects.filter(
                presenter_id=presenter_id, session=session
            ):
                if invitation.is_open:
                    cancel_invitation(invitation, actor=request.user)
            if session.status == SessionStatus.INVITED and not any(
                i.is_open for i in Invitation.objects.filter(session=session)
            ):
                session.back_to_draft()
            ActivityLog.record(
                self.conference,
                "session.presenter_removed",
                target=session,
                actor=request.user,
                presenter_id=presenter_id,
            )
        messages.success(request, f"Removed {name} from the session.")
        return redirect(session.get_absolute_url())


class SessionInviteView(OrganizerSessionActionMixin, View):
    """Send (or resend) the invitation for one presenter on this session."""

    def post(self, request, slug, link_pk):
        session = self.get_session()
        link = get_object_or_404(
            session.session_presenters.select_related("presenter"), pk=link_pk
        )
        form = InviteForm(request.POST)
        if not form.is_valid():
            messages.error(
                request, "Could not send: " + "; ".join(form.errors["message_md"])
            )
            return redirect(session.get_absolute_url())
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


class InvitationPreviewView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """The invitation email as it will be sent, rendered when an organizer
    opens an invite form and again as they write the note (htmx posts the
    form here). Rendering it on demand keeps a session page listing several
    unconfirmed presenters from building an email for each of them that
    nobody asked to see.

    ``presenter`` is a slug; ``session`` the pk of one of that presenter's
    sessions, or blank for the conference in general. Anything else falls
    back to the general invitation rather than failing: this is a preview.
    """

    def post(self, request):
        presenter = get_object_or_404(
            Presenter.objects.for_conference(self.conference),
            slug=request.POST.get("presenter", ""),
        )
        session = None
        value = request.POST.get("session", "")
        if value.isdigit():
            link = (
                presenter.session_presenters.filter(session_id=int(value))
                .select_related("session")
                .first()
            )
            session = link.session if link is not None else None
        preview = render_invitation_preview(
            Invitation(
                presenter=presenter,
                session=session,
                message_md=request.POST.get("message_md", "")[:2000],
                invited_by=request.user,
            )
        )
        return render(
            request, "speakers/_invitation_preview.html", {"preview": preview}
        )


class PresenterInviteView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """Send (or resend) an invitation from the presenter page, to a chosen
    session or to the conference in general."""

    def post(self, request, slug):
        presenter = get_object_or_404(
            Presenter.objects.for_conference(self.conference), slug=slug
        )
        form = PresenterInviteForm(request.POST, presenter=presenter)
        if not form.is_valid():
            # The form knows which session or role it refused and why, and
            # the organizer is sent back to a page that cannot show field
            # errors, so carry the reasons into the message.
            reasons = " ".join(
                error for errors in form.errors.values() for error in errors
            )
            messages.error(
                request, f"Pick a session of this edition. {reasons}".strip()
            )
            return redirect(presenter.get_absolute_url())
        session = form.cleaned_data["session"]
        if form.is_new_session:
            link = SessionPresenter.objects.create(
                session=session, presenter=presenter, role=form.cleaned_data["role"]
            )
            ActivityLog.record(
                self.conference,
                "session.presenter_added",
                target=session,
                actor=request.user,
                presenter_id=presenter.pk,
                role=link.role.code,
            )
            added = f"Added to {session.title} as {link.role.name}."
            if presenter_added_to_session(link, actor=request.user):
                # They are confirmed on it already; an invitation to accept
                # what they are confirmed on is a second email asking for
                # something that has happened. The added-to-session email
                # queued by the confirmation is the one they get.
                messages.success(
                    request,
                    f"{added} They had already accepted, so they are "
                    "confirmed on it.",
                )
                return redirect(presenter.get_absolute_url())
            added = f" {added}"
        else:
            added = ""
        invitation = (
            Invitation.objects.filter(presenter=presenter, session=session)
            .exclude(accepted_at__isnull=False)
            .order_by("-creation_date", "-id")
            .first()
        )
        resend = invitation is not None and invitation.sent_at is not None
        if invitation is None:
            invitation = Invitation(presenter=presenter, session=session)
        invitation.invited_by = request.user
        invitation.message_md = form.cleaned_data["message_md"]
        send_invitation(invitation, actor=request.user)
        messages.success(
            request,
            f"Invitation {'resent' if resend else 'sent'} to {presenter.email}."
            + added,
        )
        return redirect(presenter.get_absolute_url())


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


# ---- Speaker side -----------------------------------------------------------


def annotate_due(item, as_of):
    """Set the display attributes the checklist row reads: ``overdue``,
    ``days_left`` and ``due_tone``.

    A waiting item is never overdue, whatever its date says: nobody could
    have done it (design §9.3a).
    """
    item.overdue = (
        item.is_open
        and not item.is_waiting
        and item.due_date is not None
        and item.due_date < as_of
    )
    item.days_left = (item.due_date - as_of).days if item.due_date else None
    item.due_tone = due_tone(item)
    return item


def due_tone(item):
    """How loudly to show the due date: ``overdue``, ``soon`` (within a
    week), ``later``, or ``quiet`` once the item is no longer open."""
    if not item.is_open or item.due_date is None:
        return "quiet"
    if item.overdue:
        return "overdue"
    return "soon" if item.days_left <= 7 else "later"


def _speaker_checklist(presenter, as_of):
    """Every item the presenter can see, with overdue flags, split by side.

    ``speaker``: their own to-dos; ``organizer``: what the team does for
    them; ``video``: session-scope items (post-production) on their
    sessions. Each list is sorted by due date, undated last.
    """
    links = list(
        presenter.session_presenters.select_related(
            "session", "session__kind", "role"
        ).order_by("session__title")
    )
    items = list(
        ChecklistItem.objects.filter(
            Q(presenter=presenter)
            | Q(presenter__isnull=True, session__in=[link.session_id for link in links])
        )
        .select_related(
            "session", "assignee", "team", "completed_by", "ready_gate", "waits_for"
        )
        .order_by(F("due_date").asc(nulls_last=True), "session__title", "order", "id")
    )
    for item in items:
        annotate_due(item, as_of)
    return {
        "links": links,
        "speaker": [
            i for i in items if i.presenter_id and i.owner == ItemOwner.SPEAKER
        ],
        "organizer": [
            i for i in items if i.presenter_id and i.owner == ItemOwner.ORGANIZER
        ],
        "video": [i for i in items if i.presenter_id is None],
    }


def _session_summaries(links, speaker_items):
    """One row per session: role and how many of the speaker's own to-dos
    for it are done."""
    summaries = []
    for link in links:
        mine = [i for i in speaker_items if i.session_id == link.session_id]
        summaries.append(
            {
                "session": link.session,
                "link": link,
                "role": link.role.name,
                "done": sum(1 for i in mine if not i.is_open),
                "total": len(mine),
                # Counted in the total, never chased: the speaker sees the
                # whole run of work and is not asked for what they cannot do.
                "waiting": sum(1 for i in mine if i.is_waiting),
            }
        )
    return summaries


class SpeakerDashboardView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    """The presenter's home: their sessions with to-do progress, and the
    account and profile nudges. The checklist itself has its own page."""

    template_name = "speakers/speaker_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        presenter = self.presenter
        today_here = today(presenter.tzinfo)
        checklist = _speaker_checklist(presenter, today_here)
        open_items = [i for i in checklist["speaker"] if i.is_open]
        general = [i for i in checklist["speaker"] if i.session_id is None]
        context.update(
            {
                "conference": self.conference,
                "presenter": presenter,
                "today": today_here,
                "session_summaries": _session_summaries(
                    checklist["links"], checklist["speaker"]
                ),
                "open_count": len(open_items),
                "waiting_count": sum(1 for i in open_items if i.is_waiting),
                "general_total": len(general),
                "general_done": sum(1 for i in general if not i.is_open),
                "general_waiting": sum(1 for i in general if i.is_waiting),
                "overdue_count": sum(1 for i in open_items if i.overdue),
                "next_due": next(
                    (i for i in open_items if i.due_date and not i.is_waiting), None
                ),
                "profile_complete": bool(presenter.bio_md and presenter.headshot),
                "show_password_reminder": not self.request.user.has_usable_password()
                and not presenter.password_reminder_dismissed,
            }
        )
        return context


class SpeakerChecklistView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    """The presenter's checklist (design §2.2 and §9.5): their to-dos, what
    the team does for them, and post-production items on their sessions.

    ``?view=all`` (default) sorts everything by due date; ``?view=session``
    groups by session; ``?session=<slug>`` narrows to one session.
    """

    template_name = "speakers/speaker_checklist.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        presenter = self.presenter
        today_here = today(presenter.tzinfo)
        checklist = _speaker_checklist(presenter, today_here)
        view = "session" if self.request.GET.get("view") == "session" else "all"
        only = None
        session_param = self.request.GET.get("session")
        if session_param:
            only = next(
                (
                    link.session
                    for link in checklist["links"]
                    if link.session.slug == session_param
                ),
                None,
            )
            if only is None:
                raise Http404("Not one of your sessions.")
            view = "session"
        groups = []
        if view == "session":
            targets = [
                link.session
                for link in checklist["links"]
                if only is None or link.session_id == only.pk
            ]
            for session in targets:
                groups.append(
                    {
                        "session": session,
                        "speaker": [
                            i
                            for i in checklist["speaker"]
                            if i.session_id == session.pk
                        ],
                        "organizer": [
                            i
                            for i in checklist["organizer"]
                            if i.session_id == session.pk
                        ],
                        "video": [
                            i for i in checklist["video"] if i.session_id == session.pk
                        ],
                    }
                )
            if only is None:
                general = {
                    "session": None,
                    "speaker": [
                        i for i in checklist["speaker"] if i.session_id is None
                    ],
                    "organizer": [
                        i for i in checklist["organizer"] if i.session_id is None
                    ],
                    "video": [],
                }
                if general["speaker"] or general["organizer"]:
                    groups.insert(0, general)
            for group in groups:
                group["total"] = len(group["speaker"])
                group["done"] = sum(1 for i in group["speaker"] if not i.is_open)
        context.update(
            {
                "conference": self.conference,
                "presenter": presenter,
                "today": today_here,
                "view": view,
                "only": only,
                "groups": groups,
                "speaker_items": checklist["speaker"],
                "organizer_items": checklist["organizer"],
                "video_items": checklist["video"],
            }
        )
        return context


class SpeakerItemToggleView(LoginRequiredMixin, PresenterRequiredMixin, View):
    """Tick or untick one of the presenter's own items."""

    def post(self, request, pk):
        item = get_object_or_404(
            ChecklistItem.objects.select_related("session"),
            pk=pk,
            presenter=self.presenter,
        )
        if item.owner != ItemOwner.SPEAKER:
            raise PermissionDenied("Only your own to-dos can be ticked.")
        try:
            if item.is_open:
                complete_item(item, actor=request.user)
                messages.success(request, f"Done: {item.title}")
            elif item.status == ItemStatus.DONE:
                reopen_item(item, actor=request.user)
                messages.info(request, f"Reopened: {item.title}")
            else:
                # SKIPPED: an organizer took it off the list; only they put it back.
                messages.info(
                    request,
                    f"An organizer skipped “{item.title}”; ask them if it should "
                    "come back.",
                )
        except ChecklistError as exc:
            messages.error(request, str(exc))
        if request.headers.get("HX-Request"):
            # Swap just this row, and the notice as a toast, so the page
            # stays exactly where it is.
            return render(
                request,
                "speakers/_checklist_item_swap.html",
                {
                    "item": annotate_due(item, today(self.presenter.tzinfo)),
                    "tickable": True,
                },
            )
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}
        ):
            target = reverse("speakers:my_checklist")
        # Without JavaScript: land back on the item rather than at the top.
        return redirect(f"{target.split('#')[0]}#item-{item.pk}")


class SpeakerItemDetailView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    """One item from the presenter's lists in full: their own to-dos, the
    team's items for them, and post-production items on their sessions."""

    template_name = "speakers/speaker_item_detail.html"

    def get_item(self):
        items = ChecklistItem.objects.select_related(
            "session", "presenter", "assignee", "team", "completed_by"
        )
        item = items.filter(pk=self.kwargs["pk"], presenter=self.presenter).first()
        if item is None:
            item = get_object_or_404(
                items,
                pk=self.kwargs["pk"],
                presenter=None,
                session__session_presenters__presenter=self.presenter,
            )
        return item

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.get_item()
        today_here = today(self.presenter.tzinfo)
        item.overdue = bool(
            item.is_open and item.due_date and item.due_date < today_here
        )
        context.update(
            {
                "conference": self.conference,
                "presenter": self.presenter,
                "item": item,
                "activity": item_activity(item),
                "tickable": item.owner == ItemOwner.SPEAKER and not item.is_automatic,
                "guide": (
                    Handbook.current(self.conference, item.guide_key)
                    if item.requires_handbook
                    else None
                ),
                "rail_active": "checklist",
            }
        )
        return context


class SpeakerProfileUpdateView(LoginRequiredMixin, PresenterRequiredMixin, UpdateView):
    form_class = SpeakerProfileForm
    template_name = "speakers/speaker_profile_form.html"

    def get_object(self, queryset=None):
        return self.presenter

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["locked"] = self.presenter.identity_locked
        return kwargs

    def get_success_url(self):
        return reverse("speakers:my_profile")

    def form_valid(self, form):
        changes = _identity_changes(form, ("display_name", "slug"))
        response = super().form_valid(form)
        # Every name or address change is on record, whoever made it: a
        # co-presenter's bookmark breaks on a new address and the trail
        # must say what the old one was.
        ActivityLog.record(
            self.conference,
            "presenter.profile_updated",
            target=self.object,
            actor=self.request.user,
            **({"changes": changes} if changes else {}),
        )
        messages.success(self.request, "Your profile is saved.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["presenter"] = self.presenter
        return context


class SpeakerSessionMixin(LoginRequiredMixin, PresenterRequiredMixin):
    """A session in this edition that the presenter is on; 403 otherwise."""

    def get_session(self):
        session = get_object_or_404(
            Session.objects.for_conference(self.conference), slug=self.kwargs["slug"]
        )
        if not session.session_presenters.filter(presenter=self.presenter).exists():
            raise PermissionDenied("You are not a presenter on this session.")
        return session


class SpeakerSessionListView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    template_name = "speakers/speaker_session_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today_here = today(self.presenter.tzinfo)
        checklist = _speaker_checklist(self.presenter, today_here)
        links = list(
            self.presenter.session_presenters.select_related(
                "session", "session__kind", "role"
            )
            .prefetch_related(
                "session__session_presenters__presenter",
                # The card names each co-presenter's role, so fetch those
                # with the rows rather than one query per session.
                "session__session_presenters__role",
            )
            .order_by("session__title")
        )
        summaries = {
            summary["session"].pk: summary
            for summary in _session_summaries(links, checklist["speaker"])
        }
        for link in links:
            link.summary = summaries[link.session_id]
        context["conference"] = self.conference
        context["presenter"] = self.presenter
        context["session_links"] = links
        return context


class SpeakerSessionDetailView(SpeakerSessionMixin, TemplateView):
    """Read-only view of one of the presenter's sessions with its checklist."""

    template_name = "speakers/speaker_session_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_session()
        today_here = today(self.presenter.tzinfo)
        checklist = _speaker_checklist(self.presenter, today_here)
        link = next(row for row in checklist["links"] if row.session_id == session.pk)
        context.update(
            {
                "conference": self.conference,
                "presenter": self.presenter,
                "session": session,
                "link": link,
                "co_presenters": session.session_presenters.exclude(
                    presenter=self.presenter
                ).select_related("presenter"),
                "slot": getattr(session, "slot", None),
                "speaker_items": [
                    i for i in checklist["speaker"] if i.session_id == session.pk
                ],
                "organizer_items": [
                    i for i in checklist["organizer"] if i.session_id == session.pk
                ],
                "video_items": [
                    i for i in checklist["video"] if i.session_id == session.pk
                ],
            }
        )
        return context


class SpeakerSessionUpdateView(SpeakerSessionMixin, UpdateView):
    form_class = SpeakerSessionForm
    template_name = "speakers/speaker_session_form.html"

    # Once public (or cancelled), changes go through an organizer so the
    # public site does not change unseen.
    LOCKED = (SessionStatus.PUBLISHED, SessionStatus.CANCELLED)

    def get_object(self, queryset=None):
        session = self.get_session()
        if session.status in self.LOCKED:
            raise PermissionDenied(
                "This session is no longer editable here; ask an organizer."
            )
        return session

    def get_success_url(self):
        return reverse("speakers:my_session_detail", args=[self.object.slug])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["locked"] = self.object.identity_locked
        return kwargs

    def form_valid(self, form):
        changes = _identity_changes(form, ("title", "slug"))
        response = super().form_valid(form)
        ActivityLog.record(
            self.conference,
            "session.updated_by_presenter",
            target=self.object,
            actor=self.request.user,
            **({"changes": changes} if changes else {}),
        )
        messages.success(self.request, f"Saved “{self.object.title}”.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["presenter"] = self.presenter
        context["suggest_form"] = SuggestCoPresenterForm()
        context["co_presenters"] = self.object.session_presenters.exclude(
            presenter=self.presenter
        ).select_related("presenter")
        return context


class SuggestCoPresenterView(SpeakerSessionMixin, View):
    def post(self, request, slug):
        session = self.get_session()
        form = SuggestCoPresenterForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please give a name and a valid email address.")
            return redirect("speakers:my_session_edit", slug=session.slug)
        data = form.cleaned_data
        ActivityLog.record(
            self.conference,
            "session.copresenter_suggested",
            target=session,
            actor=request.user,
            name=data["name"],
            email=data["email"],
        )
        enqueue(
            send_copresenter_suggestion_task,
            self.presenter.pk,
            session.pk,
            data["name"],
            data["email"],
            data["note"],
        )
        messages.success(
            request, f"Thanks, we've passed {data['name']} on to the organizers."
        )
        return redirect("speakers:my_session_edit", slug=session.slug)


class SpeakerScheduleView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    """Placeholder until Stage 3 renders the schedule in the presenter's zone."""

    template_name = "speakers/speaker_schedule.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["presenter"] = self.presenter
        return context


class ProgramTypesView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView):
    """Settings: the edition's session types, what each allows, and the
    presenter roles. Organizers add to both here without a code change."""

    template_name = "speakers/program_types.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "conference": self.conference,
                "rail_active": "program_types",
                "session_types": SessionType.objects.filter(conference=self.conference)
                .select_related("default_role")
                .prefetch_related("roles"),
                "roles": PresenterRole.objects.filter(conference=self.conference),
            }
        )
        return context


class ReadinessGatesView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, ListView):
    """Settings: the switches that open checklist items nobody can start yet.

    A gate stands for work the portal cannot see: the tech check nobody can
    book until the team has the equipment, an upload that waits on a portal
    feature. Each row says how many items are waiting on it.
    """

    template_name = "speakers/readiness_gates.html"
    context_object_name = "gates"

    def get_queryset(self):
        return ReadinessGate.objects.filter(conference=self.conference).annotate(
            waiting=Count("items", filter=Q(items__is_waiting=True))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "conference": self.conference,
                "rail_active": "gates",
                "form": ReadinessGateForm(),
            }
        )
        return context


class ReadinessGateCreateView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """Add a gate to this edition. Codes are what templates name, so a
    template cloned forward finds next year's gate by the same code."""

    def post(self, request):
        form = ReadinessGateForm(request.POST)
        if not form.is_valid():
            reasons = " ".join(e for errors in form.errors.values() for e in errors)
            messages.error(request, f"That gate was not added. {reasons}".strip())
            return redirect("speakers:readiness_gates")
        gate = form.save(commit=False)
        gate.conference = self.conference
        gate.save()
        # A template line may already name this code and be holding items
        # shut for want of a gate row.
        refresh_for_conference(self.conference)
        messages.success(request, f"Added the gate “{gate.name}”.")
        return redirect("speakers:readiness_gates")


class ReadinessGateToggleView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """Open or shut one gate, then re-evaluate what was waiting on it."""

    def post(self, request, pk):
        gate = get_object_or_404(ReadinessGate, pk=pk, conference=self.conference)
        is_open = request.POST.get("open") == "1"
        if gate.set_open(is_open, actor=request.user):
            opened = refresh_readiness(ChecklistItem.objects.filter(ready_gate=gate))
            ActivityLog.record(
                self.conference,
                "checklist.gate_opened" if is_open else "checklist.gate_shut",
                actor=request.user,
                message=f"{gate.name}: {'open' if is_open else 'shut'}",
                gate_id=gate.pk,
            )
            messages.success(
                request,
                f"“{gate.name}” is {'open' if is_open else 'shut'}. "
                f"{opened} item(s) changed.",
            )
        return redirect("speakers:readiness_gates")


class ProgramTypeFormMixin(LoginRequiredMixin, SpeakerOrganizerRequiredMixin):
    """Shared by the four settings forms: edition-scoped rows, the edition
    passed to the form, back to the settings page when done."""

    def get_queryset(self):
        return self.model.objects.filter(conference=self.conference)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def get_success_url(self):
        return reverse("speakers:program_types")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "program_types"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Saved {self.object.name}.")
        return response


class SessionTypeCreateView(ProgramTypeFormMixin, CreateView):
    model = SessionType
    form_class = SessionTypeForm
    template_name = "speakers/session_type_form.html"


class SessionTypeUpdateView(ProgramTypeFormMixin, UpdateView):
    model = SessionType
    form_class = SessionTypeForm
    template_name = "speakers/session_type_form.html"


class PresenterRoleCreateView(ProgramTypeFormMixin, CreateView):
    model = PresenterRole
    form_class = PresenterRoleForm
    template_name = "speakers/presenter_role_form.html"


class PresenterRoleUpdateView(ProgramTypeFormMixin, UpdateView):
    model = PresenterRole
    form_class = PresenterRoleForm
    template_name = "speakers/presenter_role_form.html"


# ---- Organizer checklists: board, queue, item actions -----------------------


class ChecklistBoardView(LoginRequiredMixin, SpeakerStaffRequiredMixin, TemplateView):
    """Design §9.6: one tab per owner, a colour per cell, sorted by most overdue."""

    template_name = "speakers/checklist_board.html"

    def get_tab(self):
        tab = self.request.GET.get("tab", "speaker").upper()
        return tab if tab in ItemOwner.values else ItemOwner.SPEAKER

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab = self.get_tab()
        context.update(
            {
                "conference": self.conference,
                "rail_active": "checklists",
                "tab": tab,
                "sort": self.request.GET.get("sort", "overdue"),
                "board": build_board(
                    self.conference,
                    self.request.user,
                    tab,
                    sort=self.request.GET.get("sort", "overdue"),
                ),
            }
        )
        return context


class ChecklistBoardExportView(ChecklistBoardView):
    def get(self, request, *args, **kwargs):
        tab = self.get_tab()
        board = build_board(self.conference, request.user, tab)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="checklists-{tab.lower()}-{self.conference.slug}.csv"'
        )
        write_board_csv(board, response)
        return response


# How many finished items the task page shows before offering the rest.
DONE_ITEMS_SHOWN = 20


class ChecklistQueueView(LoginRequiredMixin, SpeakerQueueRequiredMixin, TemplateView):
    """My volunteering tasks: organizer items assigned to me or to a team I
    am on (design §9.6).

    It lives under the personal "My volunteering" rail for everyone,
    organizers included, because it is a person's own work rather than a
    view of the edition. ``?view=all`` (default) sorts by due date;
    ``?view=presenter`` groups by the presenter, or the session, the work
    is for.
    """

    template_name = "speakers/checklist_queue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        as_of = today()
        items = [
            annotate_due(item, as_of)
            for item in ChecklistItem.objects.filter(
                owned_by(self.request.user, self.conference),
                conference=self.conference,
                owner=ItemOwner.ORGANIZER,
                status__in=list(OPEN_ITEM_STATUSES),
            )
            .select_related("presenter", "session", "team", "ready_gate", "waits_for")
            .order_by(F("due_date").asc(nulls_last=True), "order", "id")
        ]
        view = "presenter" if self.request.GET.get("view") == "presenter" else "all"
        # What they (or their team) already finished, newest first: the
        # accomplishments list under the open items.
        # Accomplishments, not the bulk of the page: the newest few, with
        # a link to the rest, since a team member's list grows all year and
        # every row carries its own untick form.
        show_all = self.request.GET.get("completed") == "all"
        done_items = [
            annotate_due(item, as_of)
            for item in ChecklistItem.objects.filter(
                owned_by(self.request.user, self.conference),
                conference=self.conference,
                owner=ItemOwner.ORGANIZER,
                status=ItemStatus.DONE,
            )
            .select_related("presenter", "session", "team", "completed_by")
            .order_by(F("completed_at").desc(nulls_last=True), "-id")[
                : None if show_all else DONE_ITEMS_SHOWN + 1
            ]
        ]
        # One more than we show tells us whether there are more, without a
        # second query for the count.
        all_shown = show_all or len(done_items) <= DONE_ITEMS_SHOWN
        if not all_shown:
            done_items = done_items[:DONE_ITEMS_SHOWN]
        context.update(
            {
                "conference": self.conference,
                "rail_active": "queue",
                "view": view,
                "items": items,
                "groups": _queue_groups(items) if view == "presenter" else [],
                "done_items": done_items,
                "done_all_shown": all_shown,
                "done_shown": DONE_ITEMS_SHOWN,
                "today": as_of,
                # A volunteer assignee may not open a presenter page, so the
                # group headings name them without linking. The rows name
                # everyone in plain text either way.
                "can_open_pages": can_work_sessions(self.request.user, self.conference),
            }
        )
        return context


def _queue_groups(items):
    """Items grouped by who they are for: a presenter, else the session."""
    groups = {}
    for item in items:
        key = (
            ("presenter", item.presenter_id)
            if item.presenter_id
            else (
                "session",
                item.session_id,
            )
        )
        group = groups.setdefault(
            key,
            {
                "key": f"{key[0]}-{key[1]}",
                "presenter": item.presenter,
                "session": None if item.presenter_id else item.session,
                "items": [],
            },
        )
        group["items"].append(item)
    return sorted(
        groups.values(),
        key=lambda g: (
            g["presenter"].display_name if g["presenter"] else g["session"].title
        ).lower(),
    )


class ItemActionMixin(LoginRequiredMixin, SpeakerQueueRequiredMixin):
    """An item this organizer, liaison or assignee may act on."""

    def get_item(self):
        item = get_object_or_404(
            ChecklistItem.objects.select_related(
                "presenter",
                "presenter__liaison",
                "session",
                "assignee",
                "team",
                "completed_by",
            ),
            pk=self.kwargs["pk"],
            conference=self.conference,
        )
        user = self.request.user
        if is_speaker_organizer(user) or self.carries(item):
            return item
        if item.presenter is None or item.presenter.liaison_id != user.pk:
            raise PermissionDenied(
                "This item is not yours: you neither liaise its presenter nor "
                "carry it."
            )
        return item

    def carries(self, item):
        """Whether this item was handed to the actor, in person or through
        a team they are an approved member of."""
        user = self.request.user
        if item.assignee_id == user.pk:
            return True
        return (
            item.team_id is not None
            and approved_teams(user, self.conference).filter(pk=item.team_id).exists()
        )

    def respond(self, request, item, error=""):
        """An htmx request gets the refreshed row (with ``error`` shown inline,
        since a swapped row never displays queued messages); a plain form goes
        back to ``next`` when it points at this site, else to the presenter
        or session page.

        The My tasks page asks for its own row shape with ``partial=queue``.
        """
        if request.headers.get("HX-Request"):
            annotate_due(item, today())
            if request.POST.get("partial") == "queue":
                return render(
                    request,
                    "speakers/_queue_item.html",
                    {"item": item, "error": error},
                )
            return render(
                request,
                "speakers/_organizer_item_row.html",
                {
                    "item": item,
                    "owner_choices": owner_choices(self.conference),
                    "can_assign": is_speaker_organizer(request.user),
                    "error": error,
                },
            )
        if error:
            messages.error(request, error)
        # An assignee who is neither organizer nor liaison cannot open the
        # presenter or session page, so their fallback is the queue.
        if can_work_sessions(request.user, self.conference):
            fallback = (
                item.presenter.get_absolute_url()
                if item.presenter
                else item.session.get_absolute_url()
            )
        else:
            fallback = reverse("speakers:checklist_queue")
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            target = fallback
        return redirect(target)


def item_activity(item):
    """Log entries about one item. They are recorded against the presenter or
    the session with the item id in ``data``."""
    target = item.presenter or item.session
    return ActivityLog.for_target(target).filter(data__item_id=item.pk)[:20]


class ItemDetailView(ItemActionMixin, TemplateView):
    """One checklist item in full: description, who is on it, its history,
    and the actions this viewer may take. Organizers and liaisons get the
    Organize shell; a volunteer handed the item gets their personal rail."""

    template_name = "speakers/item_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.get_item()
        item.overdue = item.is_overdue
        organizer_side = can_work_sessions(self.request.user, self.conference)
        # Reassigning is organizer-only, as it is on the presenter and
        # session pages; carrying an item only lets you change its status.
        can_manage = is_speaker_organizer(self.request.user)
        context.update(
            {
                "conference": self.conference,
                "item": item,
                "activity": item_activity(item),
                "organizer_side": organizer_side,
                "can_manage": can_manage,
                "shell": (
                    "speakers/_organize_shell.html"
                    if organizer_side
                    else "portal/base_sidebar.html"
                ),
                "rail_active": "presenters" if item.presenter_id else "sessions",
                "can_override": is_speaker_organizer(self.request.user),
                "ready_override": ReadyOverride,
                "assign_form": (
                    AssignItemForm(
                        initial={"owner": item.owner_value},
                        conference=self.conference,
                    )
                    if can_manage and item.owner == ItemOwner.ORGANIZER
                    else None
                ),
            }
        )
        return context


class ItemReadyView(ItemActionMixin, View):
    """Open an item that is waiting, or hold one shut (organizers only).

    The three wait sources answer for the common case; this is the answer
    for the one they get wrong, and the log says who gave it.
    """

    def post(self, request, pk):
        if not is_speaker_organizer(request.user):
            raise PermissionDenied("Only organizers open or hold an item.")
        item = self.get_item()
        answer = request.POST.get("override", "")
        if answer not in ("", ReadyOverride.OPEN, ReadyOverride.HOLD):
            return HttpResponseBadRequest("Unknown answer.")
        item.ready_override = answer
        item.save(update_fields=["ready_override", "modified_date"])
        apply_readiness(item)
        ActivityLog.record(
            self.conference,
            "checklist.readiness_set",
            target=item.presenter or item.session,
            actor=request.user,
            message={
                ReadyOverride.OPEN: f"Opened “{item.title}”",
                ReadyOverride.HOLD: f"Held “{item.title}”",
                "": f"Left “{item.title}” to its own conditions",
            }[answer],
            item_id=item.pk,
        )
        return self.respond(request, item)


class ItemStatusView(ItemActionMixin, View):
    def post(self, request, pk):
        item = self.get_item()
        status = request.POST.get("status", "")
        note = request.POST.get("note")
        if status == ItemStatus.SKIPPED and not can_work_sessions(
            request.user, self.conference
        ):
            # Ticking an item off is one thing; deciding it does not apply,
            # with a note that may be internal, is the organizing side's
            # call. The form is hidden for a volunteer; refuse the post too.
            raise PermissionDenied("Only organizers and liaisons skip an item.")
        error = ""
        try:
            if status == ItemStatus.DONE:
                complete_item(item, actor=request.user, note=note)
            elif status == ItemStatus.TODO:
                reopen_item(item, actor=request.user)
            elif status == ItemStatus.SKIPPED:
                skip_item(item, actor=request.user, note=note)
            elif request.headers.get("HX-Request"):
                error = "Unknown status."
            else:
                return HttpResponseBadRequest("Unknown status.")
        except ChecklistError as exc:
            error = str(exc)
        return self.respond(request, item, error=error)


class ItemAssignView(ItemActionMixin, View):
    """Organizers only: a liaison ticks and skips their presenter's items but
    does not hand organizer work to someone else (#412 settled that liaisons
    do not change organizer-side data)."""

    def post(self, request, pk):
        if not is_speaker_organizer(request.user):
            raise PermissionDenied("Only organizers reassign items.")
        item = self.get_item()
        form = AssignItemForm(request.POST, conference=self.conference)
        if not form.is_valid():
            return HttpResponseBadRequest("Unknown assignee.")
        assignee, team = form.cleaned_data["owner"]
        assign_item(item, assignee=assignee, team=team, actor=request.user)
        return self.respond(request, item)


class PresenterAddItemView(PresenterScopedMixin, View):
    def post(self, request, slug):
        presenter = get_object_or_404(self.get_queryset(), slug=slug)
        form = AdhocItemForm(request.POST, conference=self.conference)
        if form.is_valid():
            assignee, team = form.cleaned_data["owner"]
            add_adhoc_item(
                self.conference,
                form.cleaned_data["title"],
                form.cleaned_data["owner_kind"],
                presenter=presenter,
                due_date=form.cleaned_data["due_date"],
                assignee=assignee,
                team=team,
                description_md=form.cleaned_data["description_md"],
                actor=request.user,
            )
            messages.success(request, f"Added “{form.cleaned_data['title']}”.")
        else:
            messages.error(request, "Could not add the item: give it a title.")
        return redirect(presenter.get_absolute_url())


class SessionAddItemView(OrganizerSessionActionMixin, View):
    """A one-off item on the session itself (post-production style)."""

    def post(self, request, slug):
        session = self.get_session()
        form = AdhocItemForm(request.POST, conference=self.conference)
        if form.is_valid():
            assignee, team = form.cleaned_data["owner"]
            add_adhoc_item(
                self.conference,
                form.cleaned_data["title"],
                form.cleaned_data["owner_kind"],
                session=session,
                due_date=form.cleaned_data["due_date"],
                assignee=assignee,
                team=team,
                description_md=form.cleaned_data["description_md"],
                actor=request.user,
            )
            messages.success(request, f"Added “{form.cleaned_data['title']}”.")
        else:
            messages.error(request, "Could not add the item: give it a title.")
        return redirect(session.get_absolute_url())


# ---- Template editor (design §9.1, task 2.6) ---------------------------------


class TemplateEditorMixin(LoginRequiredMixin, SpeakerOrganizerRequiredMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["rail_active"] = "templates"
        return context

    def get_template(self, pk):
        return get_object_or_404(
            ChecklistTemplate.objects.filter(conference=self.conference).select_related(
                "kind", "role"
            ),
            pk=pk,
        )


class ChecklistTemplateListView(TemplateEditorMixin, TemplateView):
    template_name = "speakers/template_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = list(
            ChecklistTemplate.objects.filter(conference=self.conference)
            .select_related("kind", "role")
            .annotate(item_count=Count("items"))
            .order_by("scope", "kind__sort_order", "role__sort_order", "delivery")
        )
        context["general_template"] = next(
            (t for t in templates if t.scope == ChecklistScope.GENERAL), None
        )
        context["presenter_templates"] = [
            t for t in templates if t.scope == ChecklistScope.PRESENTER
        ]
        context["session_templates"] = [
            t for t in templates if t.scope == ChecklistScope.SESSION
        ]
        return context


class ChecklistTemplateSeedView(TemplateEditorMixin, View):
    """The "Load defaults" button: an idempotent seed, on its own URL so
    the list page has no POST of its own."""

    def post(self, request):
        result = seed_checklists(self.conference)
        messages.success(
            request,
            f"Loaded {result.templates} template(s) and {result.items} item(s)."
            + (
                f" Filled in {result.described} missing description(s)."
                if result.described
                else ""
            ),
        )
        if result.skipped:
            names = "; ".join(f"{name} ({why})" for name, why in result.skipped)
            messages.warning(
                request,
                f"Skipped {len(result.skipped)}: {names}. Add the type or role "
                "under Types and roles, then load again if you want them.",
            )
        return redirect("speakers:template_list")


class ChecklistTemplateCreateView(TemplateEditorMixin, CreateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = "speakers/template_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        form.instance.conference = self.conference
        messages.success(self.request, f"Created “{form.instance.name}”.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("speakers:template_detail", args=[self.object.pk])


class ChecklistTemplateUpdateView(TemplateEditorMixin, UpdateView):
    model = ChecklistTemplate
    form_class = ChecklistTemplateForm
    template_name = "speakers/template_form.html"

    def get_queryset(self):
        return ChecklistTemplate.objects.filter(
            conference=self.conference
        ).select_related("kind", "role")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Saved “{form.instance.name}”.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("speakers:template_detail", args=[self.object.pk])


class ChecklistTemplateDetailView(TemplateEditorMixin, TemplateView):
    template_name = "speakers/template_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.get_template(self.kwargs["pk"])
        context["template"] = template
        items = list(
            template.items.annotate(instance_count=Count("instances")).order_by(
                "order", "id"
            )
        )
        wanted = {
            item.default_team_name
            for item in items
            if item.assignee_default == AssigneeDefault.TEAM and item.default_team_name
        }
        have = set(
            Team.objects.filter(
                conference=self.conference, short_name__in=wanted
            ).values_list("short_name", flat=True)
        )
        # A line naming a team this edition does not have starts its items
        # unowned and says nothing, exactly as a missing guide used to.
        context["missing_teams"] = sorted(wanted - have)
        context["items"] = items
        return context


class TemplateItemFormMixin(TemplateEditorMixin):
    form_class = ChecklistTemplateItemForm
    template_name = "speakers/template_item_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template"] = self.get_template(self.kwargs["pk"])
        return context

    def get_success_url(self):
        return reverse("speakers:template_detail", args=[self.kwargs["pk"]])


class TemplateItemCreateView(TemplateItemFormMixin, CreateView):
    model = ChecklistTemplateItem

    def form_valid(self, form):
        template = self.get_template(self.kwargs["pk"])
        form.instance.template = template
        form.instance.order = template.items.count()
        response = super().form_valid(form)
        created = apply_new_template_item(self.object)
        evaluate_items(created)
        messages.success(
            self.request,
            f"Added “{self.object.title}” to {len(created)} existing checklist(s); "
            "they will hear about it in the daily update.",
        )
        return response


class TemplateItemUpdateView(TemplateItemFormMixin, UpdateView):
    model = ChecklistTemplateItem

    def get_queryset(self):
        return ChecklistTemplateItem.objects.filter(
            template=self.get_template(self.kwargs["pk"])
        )

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["item_pk"])

    def form_valid(self, form):
        response = super().form_valid(form)
        changed = apply_template_item_changes(self.object)
        evaluate_items(
            ChecklistItem.objects.filter(template_item=self.object).select_related(
                "presenter", "session", "conference"
            )
        )
        messages.success(
            self.request,
            f"Saved “{self.object.title}”; {changed} existing item(s) updated.",
        )
        return response


class TemplateItemActionView(TemplateEditorMixin, View):
    """POST-only: move up/down or delete one template line."""

    def post(self, request, pk, item_pk, action):
        template = self.get_template(pk)
        item = get_object_or_404(template.items, pk=item_pk)
        if action == "delete":
            title = item.title
            removed = retire_template_item(item)
            item.delete()
            messages.success(
                request,
                f"Removed “{title}” from the template and {removed} open copy(ies) "
                "from existing checklists; done ones are kept.",
            )
        elif action in ("up", "down"):
            self.move(template, item, -1 if action == "up" else 1)
            sync_template_order(template)
        else:
            return HttpResponseBadRequest("Unknown action.")
        return redirect("speakers:template_detail", pk=pk)

    @staticmethod
    def move(template, item, delta):
        items = list(template.items.order_by("order", "id"))
        index = items.index(item)
        target = index + delta
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
        for position, each in enumerate(items):
            if each.order != position:
                ChecklistTemplateItem.objects.filter(pk=each.pk).update(order=position)


# ---- Pretix on the presenter page (design §12.1) -----------------------------


class PresenterPretixLookupView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View
):
    def post(self, request, slug):
        presenter = get_object_or_404(
            Presenter.objects.for_conference(self.conference), slug=slug
        )
        try:
            orders = lookup_presenter_orders(presenter, actor=request.user)
        except PretixError as exc:
            messages.error(request, f"Pretix lookup failed: {exc}")
        else:
            if orders is None:
                messages.error(request, "Pretix is not configured for this edition.")
            elif orders:
                codes = ", ".join(o.order_code for o in orders)
                messages.success(request, f"Found {len(orders)} order(s): {codes}.")
            else:
                messages.info(request, f"No pretix order under {presenter.email}.")
        return redirect(presenter.get_absolute_url())


class PresenterPretixLinkView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    def post(self, request, slug):
        presenter = get_object_or_404(
            Presenter.objects.for_conference(self.conference), slug=slug
        )
        code = request.POST.get("order_code", "").strip().upper()
        if request.POST.get("action") == "unlink":
            unlink_presenter_order(presenter, actor=request.user)
            messages.success(request, "Unlinked the pretix order.")
        elif not code:
            messages.error(request, "Give the pretix order code.")
        else:
            try:
                order = link_presenter_order(presenter, code, actor=request.user)
            except PretixError as exc:
                messages.error(request, f"Could not link order {code}: {exc}")
            else:
                messages.success(request, f"Linked order {order.order_code}.")
        return redirect(presenter.get_absolute_url())


# ---- Handbook (design §8.7, task 2.9) ---------------------------------------


class SpeakerGuideView(LoginRequiredMixin, PresenterRequiredMixin, TemplateView):
    """The guides this presenter has to read: one per guide their checklists
    require (the general speaker guide when none does), each with its own
    acknowledgement, like accepting terms of service."""

    template_name = "speakers/speaker_guide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        guides = []
        for key in required_guide_keys(self.presenter):
            handbook = Handbook.current(self.conference, key)
            if handbook is None:
                continue
            guides.append(
                {
                    "key": key,
                    "handbook": handbook,
                    "receipt": HandbookReadReceipt.objects.filter(
                        presenter=self.presenter, handbook=handbook
                    ).first(),
                }
            )
        context.update(
            {
                "conference": self.conference,
                "presenter": self.presenter,
                "guides": guides,
            }
        )
        return context


def required_guide_keys(presenter):
    """Guide keys named by the presenter's "read the guide" items, sorted.

    Empty until they have such an item: a presenter whose checklist does not
    exist yet is asked to read nothing, rather than acknowledging a guide
    their eventual checklist may never name.
    """
    keys = {
        key or DEFAULT_GUIDE_KEY
        for key in ChecklistItem.objects.filter(
            presenter=presenter, auto_complete_rule=AutoRule.HANDBOOK_READ
        ).values_list("requires_handbook", flat=True)
    }
    return sorted(keys)


def required_handbook_keys(conference):
    """Every guide key this edition's checklists ask for, from the templates
    and from items already handed out. A blank key means the default guide."""
    template_keys = ChecklistTemplateItem.objects.filter(
        template__conference=conference, auto_complete_rule=AutoRule.HANDBOOK_READ
    ).values_list("requires_handbook", flat=True)
    item_keys = ChecklistItem.objects.filter(
        conference=conference,
        auto_complete_rule=AutoRule.HANDBOOK_READ,
        status__in=list(OPEN_ITEM_STATUSES),
    ).values_list("requires_handbook", flat=True)
    return {key or DEFAULT_GUIDE_KEY for key in [*template_keys, *item_keys]}


class SpeakerGuideReadView(LoginRequiredMixin, PresenterRequiredMixin, View):
    """The explicit acknowledgement for one guide: the presenter ticks the
    box and confirms they read its current version."""

    def post(self, request):
        key = request.POST.get("key", DEFAULT_GUIDE_KEY)
        handbook = (
            Handbook.current(self.conference, key)
            if key in required_guide_keys(self.presenter)
            else None
        )
        if handbook is None:
            return HttpResponseBadRequest("No such published guide for you.")
        if not request.POST.get("acknowledge"):
            messages.error(request, "Tick the box to confirm you have read the guide.")
            return redirect("speakers:my_guide")
        _, created = handbook.record_read(self.presenter)
        if created:
            ActivityLog.record(
                self.conference,
                "handbook.read",
                target=self.presenter,
                actor=request.user,
                key=handbook.key,
                version=handbook.version,
            )
        messages.success(
            request, f"Thanks, we've noted that you read {handbook.title}."
        )
        return redirect("speakers:my_guide")


class HandbookListView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView):
    """All guides of the edition, and a form to start another one."""

    template_name = "speakers/handbook_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        existing = Handbook.keys(self.conference)
        rows = []
        for key, title in existing:
            current = Handbook.current(self.conference, key)
            rows.append(
                {
                    "key": key,
                    "title": title,
                    "current": current,
                    "draft": Handbook.draft(self.conference, key),
                    "readers": current.receipts.count() if current else 0,
                }
            )
        referenced = required_handbook_keys(self.conference)
        if not referenced and not existing:
            # Nothing written and no checklist asking yet: still offer the
            # default guide, so a fresh edition has somewhere to start.
            referenced = {DEFAULT_GUIDE_KEY}
        missing = sorted(referenced - {key for key, _ in existing})
        rows += [{"key": key, "missing": True} for key in missing]
        context.update(
            {
                "conference": self.conference,
                "rail_active": "handbook",
                "rows": rows,
                "missing_count": len(missing),
                "new_form": kwargs.get("new_form") or self.prefilled_form(),
            }
        )
        return context

    def prefilled_form(self):
        """The add form, filled in when an organizer clicks "start this
        guide" on a key the checklists ask for but nobody has written."""
        key = self.request.GET.get("key", "")
        initial = (
            {"key": key, "title": f"{key.replace('-', ' ').capitalize()} guide"}
            if key
            else None
        )
        return NewHandbookForm(conference=self.conference, initial=initial)

    def post(self, request):
        form = NewHandbookForm(request.POST, conference=self.conference)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(new_form=form))
        # A new guide starts unpublished and pointed at the conference's
        # docs index. That placeholder satisfies the editor's "a link or a
        # note" check, which is deliberate: an organizer may publish a guide
        # that only says "see the docs" and refine the address later.
        Handbook.objects.create(
            conference=self.conference,
            key=form.cleaned_data["key"],
            title=form.cleaned_data["title"],
            url=DEFAULT_GUIDE_URL,
        )
        messages.success(request, f"Started the {form.cleaned_data['title']} guide.")
        return redirect("speakers:handbook_editor", key=form.cleaned_data["key"])


class HandbookEditorView(
    LoginRequiredMixin, SpeakerOrganizerRequiredMixin, TemplateView
):
    """Write the next version of one guide as a draft, publish it when ready."""

    template_name = "speakers/handbook_editor.html"

    @property
    def key(self):
        return self.kwargs["key"]

    def get_draft(self):
        return Handbook.draft(self.conference, self.key)

    def get_form(self, data=None):
        draft = self.get_draft()
        if draft is not None:
            return HandbookForm(data, instance=draft)
        current = Handbook.current(self.conference, self.key)
        initial = (
            {"title": current.title, "url": current.url, "body_md": current.body_md}
            if current
            else {"url": DEFAULT_GUIDE_URL}
        )
        return HandbookForm(data, initial=initial)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        versions = list(
            Handbook.objects.filter(conference=self.conference, key=self.key)
            .annotate(reader_count=Count("receipts"))
            .order_by("-version")
        )
        if not versions and self.key != DEFAULT_GUIDE_KEY:
            raise Http404("No such guide.")
        context.update(
            {
                "conference": self.conference,
                "rail_active": "handbook",
                "key": self.key,
                "form": kwargs.get("form") or self.get_form(),
                "current": Handbook.current(self.conference, self.key),
                "draft": self.get_draft(),
                "versions": versions,
            }
        )
        return context

    def post(self, request, key):
        form = self.get_form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        handbook = form.save(commit=False)
        if handbook.pk is None:
            handbook.conference = self.conference
            handbook.key = key
            handbook.version = Handbook.next_version(self.conference, key)
        if request.POST.get("action") == "publish":
            if not handbook.url and not handbook.body_md.strip():
                form.add_error(
                    "url", "Give a link or write the guide before publishing."
                )
                return self.render_to_response(self.get_context_data(form=form))
            handbook.publish()
            ActivityLog.record(
                self.conference,
                "handbook.published",
                target=handbook,
                actor=request.user,
                key=key,
                version=handbook.version,
            )
            messages.success(
                request,
                f"Published {handbook.title} version {handbook.version}. Presenters "
                "who read an earlier version have their guide item re-opened.",
            )
        else:
            handbook.save()
            messages.success(request, f"Saved draft version {handbook.version}.")
        return redirect("speakers:handbook_editor", key=key)


# ---- Onboarding after acceptance (2.16) --------------------------------------


class SpeakerWelcomeView(LoginRequiredMixin, PresenterRequiredMixin, FormView):
    """Account details, agreements and an optional password, before the
    dashboard.

    The skip asks the same question the gate does. Keying it on "has a
    portal profile" instead used to bounce a presenter whose profile
    predates the agreements between this page and the dashboard forever:
    the gate sent them here, here sent them back.
    """

    template_name = "speakers/speaker_welcome.html"
    form_class = SpeakerOnboardingForm

    def get(self, request, *args, **kwargs):
        if agreements.has_agreed(request.user):
            return redirect("speakers:my_dashboard")
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        user = self.request.user
        first, _, last = self.presenter.display_name.partition(" ")
        return {
            "username": user.username,
            "first_name": user.first_name or first,
            "last_name": user.last_name or last,
            "pronouns": self.presenter.pronouns,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["presenter"] = self.presenter
        return context

    def form_valid(self, form):
        form.save()
        if form.sets_password:
            update_session_auth_hash(self.request, self.request.user)
            self.presenter.password_reminder_dismissed = True
            self.presenter.save(
                update_fields=["password_reminder_dismissed", "modified_date"]
            )
        ActivityLog.record(
            self.conference,
            "presenter.onboarded",
            target=self.presenter,
            actor=self.request.user,
            password_set=form.sets_password,
        )
        messages.success(
            self.request,
            "Welcome! Your account is ready."
            + (
                ""
                if form.sets_password
                else " You can sign in with an emailed code any time."
            ),
        )
        return redirect("speakers:my_dashboard")


class DismissPasswordReminderView(LoginRequiredMixin, PresenterRequiredMixin, View):
    def post(self, request):
        self.presenter.password_reminder_dismissed = True
        self.presenter.save(
            update_fields=["password_reminder_dismissed", "modified_date"]
        )
        messages.info(
            request,
            "Fine by us: sign-in codes it is. You can set a password later under Manage account.",
        )
        return redirect("speakers:my_dashboard")
