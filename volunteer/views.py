import django_filters
import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from common.mixins import (
    AdminRequiredMixin,
    TeamLeadRequiredMixin,
    VolunteerOrAdminRequiredMixin,
)
from common.tasks import enqueue
from portal.common import (
    get_volunteer_languages_stat_cache,
    get_volunteer_onboarded_stat_cache,
    get_volunteer_teams_stat_cache,
)
from portal.models import Conference
from speakers.models import speaker_module_enabled
from speakers.permissions import can_work_queue
from speakers.stats import my_task_stats

from .forms import TeamForm, VolunteerProfileForm, VolunteerProfileReviewForm
from .models import (  # Language,
    ApplicationStatus,
    PyladiesChapter,
    Team,
    VolunteerProfile,
)
from .tasks import (
    send_volunteer_cancelled_emails_task,
    send_volunteer_onboarding_email_task,
)


@login_required
def index(request):
    context = {}
    # One profile per conference; show the active edition's.
    profile = VolunteerProfile.objects.filter(
        user=request.user, conference=Conference.get_active()
    ).first()
    context["profile"] = profile

    # Personal hub data: the teams this volunteer is on, and which of those they
    # lead (so the template can link leads to the team dashboard from slice 1).
    if profile:
        context["my_teams"] = list(profile.teams.all())
        context["led_team_ids"] = set(profile.team_leads.values_list("id", flat=True))
    else:
        context["my_teams"] = []
        context["led_team_ids"] = set()

    # Editions volunteered for = one profile per conference for this user.
    context["conferences_count"] = VolunteerProfile.objects.filter(
        user=request.user
    ).count()
    # Their volunteering tasks (speaker-portal items assigned to them or a
    # team they are on), when the module is on and they may open the list.
    conference = Conference.get_active()
    context["task_stats"] = (
        my_task_stats(request.user, conference)
        if speaker_module_enabled(conference)
        and can_work_queue(request.user, conference)
        else None
    )
    return render(request, "volunteer/index.html", context)


class MyConferencesView(ListView):
    """List every edition the logged-in volunteer has a profile for."""

    template_name = "volunteer/my_conferences.html"
    context_object_name = "profiles"

    def get_queryset(self):
        return (
            VolunteerProfile.objects.filter(user=self.request.user)
            .select_related("conference")
            .prefetch_related("teams", "roles")
            .order_by("-conference__year")
        )


class VolunteerAdminRequiredMixin(AdminRequiredMixin):
    """Mixin for views that require administrative permission for the volunteers.
    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """


class VolunteerProfileFilter(django_filters.FilterSet):

    search = django_filters.CharFilter(
        label="Search by username, first name, or last name", method="search_fulltext"
    )
    # temporarily disable the language filter
    # language = django_filters.ChoiceFilter(
    #     method="filter_language",
    #     label="Language",
    #     field_name="language",
    #     choices=language_choices,
    # )

    class Meta:
        model = VolunteerProfile
        fields = ["search", "application_status"]

    def search_fulltext(self, queryset, field_name, value):
        if not value:
            return queryset
        return queryset.annotate(  # pragma: no cover
            search=SearchVector("user__username", "user__first_name", "user__last_name")
        ).filter(search=SearchQuery(value))

    # def filter_language(self, queryset, name, value):
    #     """Custom filtering for the languages field."""
    #     return queryset.filter(language__code=value)


class VolunteerProfileTable(tables.Table):
    """Compact review queue, like the team and conference lists: who applied,
    where they landed, what state they're in, and the action. Everything else
    (Discord, roles, dates) lives on the profile detail and review pages."""

    actions = tables.Column(accessor="id", verbose_name="Actions")
    username = tables.Column(accessor="user__username", verbose_name="Username")
    name = tables.Column(accessor="user__first_name", verbose_name="Name")
    teams = tables.Column(accessor="teams", verbose_name="Teams")

    class Meta:
        model = VolunteerProfile
        fields = (
            "username",
            "name",
            "teams",
            "application_status",
            "actions",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_application_status(self, value):
        """Render the application status with a badge."""
        if value == ApplicationStatus.APPROVED:
            return format_html('<span class="badge bg-success">{}</span>', value)
        elif value == ApplicationStatus.REJECTED:
            return format_html('<span class="badge bg-danger">{}</span>', value)
        elif value == ApplicationStatus.CANCELLED:
            return format_html('<span class="badge bg-secondary">{}</span>', value)
        else:
            return format_html('<span class="badge bg-warning">{}</span>', value)

    def render_actions(self, value, record):
        """Render the actions column.
        If the application status is Pending, render the Review button.
        If the application status is Approved, render the Manage volunteer button.
        """
        render_html = ""
        application_status = record.application_status
        url = reverse("volunteer:volunteer_profile_manage", kwargs={"pk": record.pk})
        if application_status in [
            ApplicationStatus.PENDING,
            ApplicationStatus.WAITLISTED,
        ]:
            render_html = format_html(
                '<a href="{}" class="btn btn-sm btn-primary" title="Review" '
                'aria-label="Review"><i class="fa-solid fa-clipboard-list"></i></a> ',
                url,
            )
        elif application_status == ApplicationStatus.APPROVED:
            render_html = format_html(
                '<a href="{}" class="btn btn-sm btn-info" title="Manage" '
                'aria-label="Manage"><i class="fa-solid fa-gear"></i></a> ',
                url,
            )
        return render_html

    def render_username(self, value, record):
        """Render the username as a link to the user's profile."""
        detail_url = reverse(
            "volunteer:volunteer_profile_detail", kwargs={"pk": record.pk}
        )
        html_content = format_html(
            '<a href="{}">{}</a>', detail_url, record.user.username
        )

        if record.user.is_superuser:
            html_content = format_html(
                '{} <i class="fa-solid fa-user-secret"></i>', html_content
            )
        return html_content

    def render_teams(self, value, record):
        """Render the teams as badges with links to team detail pages."""
        html_content = ""
        for team in record.teams.all():
            team_url = reverse("team_detail", kwargs={"pk": team.pk})
            html_content = format_html(
                '{}<a href="{}" class="badge bg-secondary">{}</a> ',
                html_content,
                team_url,
                team.short_name,
            )
        return html_content

    def render_name(self, value, record):
        """Render the volunteer's full name."""
        return record.user.get_full_name()


class VolunteerProfileList(VolunteerAdminRequiredMixin, SingleTableMixin, FilterView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_list.html"
    table_class = VolunteerProfileTable
    filterset_class = VolunteerProfileFilter

    def get_selected_conference(self):
        """The conference whose volunteers are shown; defaults to active.

        Admins can switch years via ``?conference=<pk>``.
        """
        param = self.request.GET.get("conference")
        if param:
            return Conference.objects.filter(pk=param).first()
        return Conference.get_active()

    def get_queryset(self):
        # ``conference=None`` matches nothing, so an unknown year or no active
        # conference yields an empty list rather than every year at once.
        return super().get_queryset().filter(conference=self.get_selected_conference())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conferences"] = Conference.objects.all()
        context["selected_conference"] = self.get_selected_conference()
        return context


class VolunteerProfileView(DetailView):
    model = VolunteerProfile

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except Http404:
            return redirect("volunteer:index")
        if (
            not self.object
            or self.object.user != request.user
            and not request.user.is_staff
        ):
            return redirect("volunteer:index")
        return super(VolunteerProfileView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The personal rail belongs to the profile's owner; staff viewing
        # someone else's profile get the plain layout instead.
        context["is_own_profile"] = self.object.user == self.request.user
        return context


class ManageVolunteerProfile(VolunteerAdminRequiredMixin, UpdateView):
    """View for managing a volunteer profile.

    Only accessible to staff or superusers.
    Only allows updating a profile that has been approved.
    """

    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_review_form.html"
    success_url = reverse_lazy("volunteer:volunteer_profile_list")
    form_class = VolunteerProfileReviewForm

    def get_form_kwargs(self):
        kwargs = super(ManageVolunteerProfile, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Prior-year applications by the same volunteer, newest first, to inform
        # the review decision (what years/roles they served before).
        context["volunteer_history"] = (
            VolunteerProfile.objects.filter(user=self.object.user)
            .exclude(pk=self.object.pk)
            .select_related("conference")
            .prefetch_related("roles", "teams")
            .order_by("-conference__year")
        )
        return context


class VolunteerProfileCreate(CreateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_form.html"
    success_url = reverse_lazy("volunteer:index")
    form_class = VolunteerProfileForm

    def dispatch(self, request, *args, **kwargs):
        # Volunteer profiles are tied to the active edition; with none active
        # there is nothing to sign up for, so don't offer (or accept) the form.
        if request.user.is_authenticated and Conference.get_active() is None:
            messages.info(
                request,
                "Volunteer sign-ups open once the next conference is active.",
            )
            return redirect("volunteer:index")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        # Only block if they have already applied for the *active* conference;
        # returning volunteers may apply afresh each year.
        if VolunteerProfile.objects.filter(
            user=request.user, conference=Conference.get_active()
        ).exists():
            return redirect("volunteer:index")
        return super(VolunteerProfileCreate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(VolunteerProfileCreate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class VolunteerProfileUpdate(UpdateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_form.html"
    success_url = reverse_lazy("volunteer:index")
    form_class = VolunteerProfileForm

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except Http404:
            return redirect("volunteer:index")
        if not self.object or self.object.user != request.user:
            return redirect("volunteer:index")
        return super(VolunteerProfileUpdate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(VolunteerProfileUpdate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class VolunteerProfileDelete(DeleteView):
    model = VolunteerProfile
    success_url = reverse_lazy("volunteer:index")


class TeamList(VolunteerAdminRequiredMixin, ListView):
    model = Team
    template_name = "team/index.html"
    context_object_name = "teams"

    def get_selected_conference(self):
        """The edition whose teams are shown; ``?conference=<pk>`` switches it."""
        param = self.request.GET.get("conference")
        if param:
            conference = Conference.objects.filter(pk=param).first()
            if conference is not None:
                return conference
        return Conference.get_active()

    def get_queryset(self):
        # ``conference=None`` matches nothing, so no active edition yields an
        # empty list rather than mixing every year's teams together.
        return Team.objects.filter(conference=self.get_selected_conference())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conference = self.get_selected_conference()
        context["conferences"] = Conference.objects.all()
        context["selected_conference"] = conference

        teams = context["teams"]
        if conference:
            context["onboarded_count"] = get_volunteer_onboarded_stat_cache(conference)
            context["teams_count"] = get_volunteer_teams_stat_cache(conference)
            context["languages_count"] = get_volunteer_languages_stat_cache(conference)
        else:
            context["onboarded_count"] = 0
            context["teams_count"] = 0
            context["languages_count"] = 0

        # Cross-team aggregates the bare list never surfaced.
        context["pending_total"] = sum(t.pending_members.count() for t in teams)
        context["open_count"] = sum(1 for t in teams if t.open_to_new_members)
        context["unled_count"] = sum(1 for t in teams if not t.team_leads.exists())
        return context


class TeamView(VolunteerAdminRequiredMixin, DetailView):
    model = Team
    template_name = "team/team_detail.html"
    context_object_name = "team"

    def get(self, request, pk):
        try:
            self.object = Team.objects.get(pk=pk)
        except Team.DoesNotExist:
            return redirect("teams")
        return super(TeamView, self).get(request, pk)


class TeamDashboardView(TeamLeadRequiredMixin, DetailView):
    """Internal management dashboard for a single team.

    Reachable by an admin (superuser/staff) or a lead of this team. Surfaces the
    same stat-card pattern as the sponsorship list, then the roster split into
    pending / waitlisted / approved.

    Two distinct capability flags drive the template:

    * ``can_manage_members`` — admin OR a lead of this team. Controls whether
      the pending/waitlisted rosters and member detail links are shown. Leads
      need this visibility into who is waiting on their team.
    * ``is_admin`` — superuser/staff only. Controls the approve/manage *action*
      buttons, which link to ``ManageVolunteerProfile`` (admin-only today).
      Keeping approval admin-only matches the "recommend, don't approve"
      default for leads; flip these to ``can_manage_members`` if/when leads are
      allowed to approve their own members.
    """

    model = Team
    template_name = "team/team_dashboard.html"
    context_object_name = "team"

    def get(self, request, *args, **kwargs):
        try:
            self.object = Team.objects.get(pk=kwargs.get("pk"))
        except Team.DoesNotExist:
            return redirect("teams")
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = self.object
        user = self.request.user
        is_admin = user.is_superuser or user.is_staff

        context["approved"] = team.approved_members
        context["pending"] = team.pending_members
        context["waitlisted"] = team.waitlisted_members
        context["is_admin"] = is_admin
        context["can_manage_members"] = (
            is_admin or team.team_leads.filter(user=user).exists()
        )

        # Applicants who applied to this edition without picking a team. A lead
        # can pull one onto their team; no other roster surfaces them.
        context["unassigned_applicants"] = (
            VolunteerProfile.objects.filter(
                conference=team.conference,
                application_status=ApplicationStatus.PENDING,
                teams__isnull=True,
            )
            .select_related("user")
            .order_by("user__username")
        )
        return context


class AddApplicantToTeamView(TeamLeadRequiredMixin, View):
    """Let a lead (or admin) pull an unassigned applicant onto their team.

    Scoped by ``TeamLeadRequiredMixin`` to the team in the URL. Only a genuinely
    unassigned, pending applicant from the same edition can be added; they join
    the team's pending roster and still go through the normal approval.
    """

    def post(self, request, pk, profile_pk):
        team = Team.objects.filter(pk=pk).first()
        if team is None:
            return redirect("teams")

        applicant = VolunteerProfile.objects.filter(pk=profile_pk).first()
        if (
            applicant is None
            or applicant.conference_id != team.conference_id
            or applicant.application_status != ApplicationStatus.PENDING
            or applicant.teams.exists()
        ):
            messages.warning(
                request, "That volunteer is no longer available to add to this team."
            )
            return redirect("team_dashboard", pk=team.pk)

        applicant.teams.add(team)
        name = applicant.user.get_full_name() or applicant.user.username
        messages.success(request, f"Added {name} to {team.short_name}.")
        return redirect("team_dashboard", pk=team.pk)


# Applications that ended in a no: the team stays in the data, but it is
# not one of "my teams".
SETTLED_AGAINST = (ApplicationStatus.REJECTED, ApplicationStatus.CANCELLED)


class MyTeamsView(LoginRequiredMixin, ListView):
    """Teams the current user is on, across every edition: the ones they
    lead (linked to the team dashboard) and the ones they are a member of,
    including applications still under review, which are Pending and
    Waitlisted.

    An edition whose application was rejected or cancelled is left out. The
    team row survives the decision, so it would otherwise sit on this page
    as a standing reminder of a "no", and there is nothing to do with it.
    The team dashboard link stays with leads.

    The "My teams" nav entry (gated on ``leads_any_team``) and the personal
    rail both point here.
    """

    model = Team
    template_name = "team/my_teams.html"
    context_object_name = "teams"

    def get_queryset(self):
        user = self.request.user
        # The three counts the page shows come back with the row rather
        # than one query each: this list grows with the editions someone
        # has volunteered for.
        return (
            Team.objects.filter(Q(team_leads__user=user) | Q(members__user=user))
            .select_related("conference")
            .annotate(
                approved_count=Count(
                    "members",
                    filter=Q(members__application_status=ApplicationStatus.APPROVED),
                    distinct=True,
                ),
                pending_count=Count(
                    "members",
                    filter=Q(members__application_status=ApplicationStatus.PENDING),
                    distinct=True,
                ),
                waitlisted_count=Count(
                    "members",
                    filter=Q(members__application_status=ApplicationStatus.WAITLISTED),
                    distinct=True,
                ),
            )
            .order_by("-conference__year", "short_name")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        led_ids = set(
            Team.objects.filter(team_leads__user=user).values_list("id", flat=True)
        )
        status_by_conference = dict(
            VolunteerProfile.objects.filter(user=user).values_list(
                "conference_id", "application_status"
            )
        )
        context["rows"] = [
            row
            for row in (
                {
                    "team": team,
                    "is_lead": team.id in led_ids,
                    "status": status_by_conference.get(team.conference_id),
                }
                for team in context["teams"]
            )
            # A lead keeps their team whatever their own application says.
            if row["is_lead"] or row["status"] not in SETTLED_AGAINST
        ]
        return context


class TeamCreate(VolunteerAdminRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = "team/team_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # A hint for the form's default conference; the field is now selectable.
        kwargs["conference"] = Conference.get_active()
        return kwargs

    def get_success_url(self):
        return reverse("team_detail", kwargs={"pk": self.object.pk})


class TeamUpdate(VolunteerAdminRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = "team/team_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.object.conference
        return kwargs

    def get_success_url(self):
        return reverse("team_detail", kwargs={"pk": self.object.pk})


class TeamDelete(VolunteerAdminRequiredMixin, DeleteView):
    model = Team
    template_name = "team/team_confirm_delete.html"
    success_url = reverse_lazy("teams")


class ResendOnboardingEmailView(VolunteerAdminRequiredMixin, View):

    def post(self, request, pk):
        """
        Resend the onboarding email to the volunteer.
        """
        try:
            profile = VolunteerProfile.objects.get(pk=pk)
            if profile.application_status == ApplicationStatus.APPROVED:
                enqueue(send_volunteer_onboarding_email_task, profile.id)
                messages.add_message(
                    request, messages.SUCCESS, "Onboarding email was sent successfully."
                )
            else:

                messages.add_message(
                    request,
                    messages.ERROR,
                    "Onboarding email can only be sent to approved volunteers.",
                )
        except VolunteerProfile.DoesNotExist:
            messages.add_message(
                request, messages.ERROR, "Volunteer profile not found."
            )

        except Exception as e:  # pragma: no cover

            messages.add_message(
                request, messages.ERROR, f"An error occurred: {str(e)}"
            )

        return redirect("volunteer:volunteer_profile_manage", pk=pk)


class CancelVolunteeringView(VolunteerOrAdminRequiredMixin, View):
    """View to handle volunteer application cancellation."""

    def post(self, request, pk):
        try:
            profile = VolunteerProfile.objects.get(pk=pk)

            # Check if already canceled
            if profile.application_status == ApplicationStatus.CANCELLED:
                messages.add_message(
                    request,
                    messages.WARNING,
                    "This volunteer application is already cancelled.",
                )
                return redirect("volunteer:volunteer_profile_detail", pk=pk)

            # Capture team/role ids before clearing; the task re-fetches them
            # for the notification emails (the rows persist, only membership
            # is removed).
            team_ids = list(profile.teams.values_list("id", flat=True))
            role_ids = list(profile.roles.values_list("id", flat=True))
            # Update the volunteer profile
            profile.application_status = ApplicationStatus.CANCELLED
            profile.teams.clear()  # Remove from all teams
            profile.roles.clear()  # Remove from all roles
            profile.save()

            enqueue(
                send_volunteer_cancelled_emails_task, profile.id, team_ids, role_ids
            )

            messages.add_message(
                request,
                messages.SUCCESS,
                "Your volunteer application has been cancelled successfully.",
            )

            # Redirect based on user type
            if request.user.is_staff or request.user.is_superuser:
                return redirect("volunteer:volunteer_profile_list")
            else:
                return redirect("volunteer:index")

        except Exception as e:
            messages.add_message(
                request, messages.ERROR, f"An error occurred while cancelling: {str(e)}"
            )
            return redirect("volunteer:volunteer_profile_detail", pk=pk)


class ReapplyVolunteeringView(VolunteerOrAdminRequiredMixin, View):
    """Re-open a previously cancelled volunteer application.

    Cancelling keeps the profile row (for the edition it was for), so a
    volunteer can rejoin without starting over: flip it back to pending and send
    them to the form to refresh their details and pick teams again.
    """

    def post(self, request, pk):
        profile = VolunteerProfile.objects.filter(pk=pk).first()
        if profile is None:
            return redirect("volunteer:index")
        if profile.application_status != ApplicationStatus.CANCELLED:
            messages.info(request, "This volunteer application is already active.")
            return redirect("volunteer:index")

        profile.application_status = ApplicationStatus.PENDING
        profile.save()
        messages.success(
            request,
            "Welcome back! Your application is under review again — "
            "update your profile to pick the teams you'd like to join.",
        )
        return redirect("volunteer:volunteer_profile_edit", pk=profile.pk)


class PyladiesChaptersList(ListView):
    """View to display all the PyLadies Chapters we have in the System."""

    model = PyladiesChapter
    template_name = "pyladies_chapter/index.html"
    context_object_name = "pyladies_chapters"
