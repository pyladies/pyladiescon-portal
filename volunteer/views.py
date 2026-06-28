import django_filters
import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
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
from portal.models import Conference

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
    # A user can have one profile per conference; show the active edition's.
    # ``conference=None`` (no active conference) matches nothing, so this
    # safely yields no profile rather than an arbitrary year.
    context["profile"] = VolunteerProfile.objects.filter(
        user=request.user, conference=Conference.get_active()
    ).first()
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

    date_joined = tables.Column(
        accessor="user__date_joined", verbose_name="Joined Date"
    )
    application_date = tables.Column(
        accessor="creation_date", verbose_name="Application Date"
    )
    updated_date = tables.Column(
        accessor="modified_date", verbose_name="Application Last Updated"
    )
    discord_username = tables.Column(
        accessor="discord_username", verbose_name="Discord Username"
    )
    actions = tables.Column(accessor="id", verbose_name="Actions")
    username = tables.Column(accessor="user__username", verbose_name="Username")
    teams = tables.Column(accessor="teams", verbose_name="Teams")
    roles = tables.Column(accessor="roles", verbose_name="Roles")

    class Meta:
        model = VolunteerProfile
        fields = (
            "username",
            "user__first_name",
            "user__last_name",
            "discord_username",
            "teams",
            "roles",
            "date_joined",
            "application_date",
            "updated_date",
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

    def render_roles(self, value, record):
        """Render the roles as badges."""
        html_content = ""
        for role in record.roles.all():
            html_content = format_html(
                '{}<span class="badge bg-secondary">{}</span> ',
                html_content,
                role.short_name,
            )
        return html_content


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
        context["conferences"] = Conference.objects.all()
        context["selected_conference"] = self.get_selected_conference()
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
        return context


class MyTeamsView(LoginRequiredMixin, ListView):
    """Teams the current user leads, across every edition.

    A one-screen landing for leads: each team links to its dashboard. The "My
    teams" nav entry (gated on ``leads_any_team``) points here.
    """

    model = Team
    template_name = "team/my_teams.html"
    context_object_name = "teams"

    def get_queryset(self):
        return (
            Team.objects.filter(team_leads__user=self.request.user)
            .select_related("conference")
            .order_by("-conference__year", "short_name")
            .distinct()
        )


class TeamCreate(VolunteerAdminRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = "team/team_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = Conference.get_active()
        return kwargs

    def form_valid(self, form):
        # New teams belong to the active edition.
        form.instance.conference = Conference.get_active()
        return super().form_valid(form)

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


class PyladiesChaptersList(ListView):
    """View to display all the PyLadies Chapters we have in the System."""

    model = PyladiesChapter
    template_name = "pyladies_chapter/index.html"
    context_object_name = "pyladies_chapters"
