import django_filters
import django_tables2 as tables
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
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

from .forms import VolunteerProfileForm, VolunteerProfileReviewForm
from .languages import LANGUAGES
from .models import (
    ApplicationStatus,
    Team,
    VolunteerProfile,
    send_volunteer_onboarding_email,
)


@login_required
def index(request):
    context = {}
    try:
        profile = VolunteerProfile.objects.get(user=request.user)
        context["profile"] = profile
    except VolunteerProfile.DoesNotExist:
        context["profile"] = None
    return render(request, "volunteer/index.html", context)


class VolunteerAdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require administrative permission for the volunteers.
    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff


class VolunteerProfileFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        label="Search by username, first name, or last name", method="search_fulltext"
    )
    languages_spoken = django_filters.ChoiceFilter(
        method="filter_languages_spoken",
        choices=LANGUAGES,
        label="Languages Spoken",
        field_name="languages_spoken",
    )

    class Meta:
        model = VolunteerProfile
        fields = ["search", "application_status"]

    def search_fulltext(self, queryset, field_name, value):
        if not value:
            return queryset
        return queryset.annotate(  # pragma: no cover
            search=SearchVector("user__username", "user__first_name", "user__last_name")
        ).filter(search=SearchQuery(value))

    def filter_languages_spoken(self, queryset, name, value):
        """Custom filtering for the languages_spoken field."""
        return queryset.filter(languages_spoken__contains=[value])


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
        if application_status == ApplicationStatus.PENDING:
            render_html = format_html(
                '<a href="{}" class="btn btn-sm btn-primary">Review</a> ', url
            )
        elif application_status == ApplicationStatus.APPROVED:
            render_html = format_html(
                '<a href="{}" class="btn btn-sm btn-info">Manage</a> ', url
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

    def get_queryset(self):
        """Filter out cancelled applications by default."""
        return (
            super()
            .get_queryset()
            .exclude(application_status=ApplicationStatus.CANCELLED)
        )


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


class VolunteerProfileCreate(CreateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_form.html"
    success_url = reverse_lazy("volunteer:index")
    form_class = VolunteerProfileForm

    def get(self, request, *args, **kwargs):
        if VolunteerProfile.objects.filter(user__id=request.user.id).exists():
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


class ResendOnboardingEmailView(VolunteerAdminRequiredMixin, View):

    def post(self, request, pk):
        """
        Resend the onboarding email to the volunteer.
        """
        try:
            profile = VolunteerProfile.objects.get(pk=pk)
            if profile.application_status == ApplicationStatus.APPROVED:
                send_volunteer_onboarding_email(profile)
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


class CancelVolunteeringView(View):
    """View to handle volunteer application cancellation."""

    def post(self, request, pk):
        try:
            profile = VolunteerProfile.objects.get(pk=pk)

            # Check permissions - only the volunteer themselves or staff can cancel
            if profile.user != request.user and not (
                request.user.is_staff or request.user.is_superuser
            ):
                messages.add_message(
                    request,
                    messages.ERROR,
                    "You don't have permission to cancel this volunteer application.",
                )
                return redirect("volunteer:index")

            # Check if already cancelled
            if profile.application_status == ApplicationStatus.CANCELLED:
                messages.add_message(
                    request,
                    messages.WARNING,
                    "This volunteer application is already cancelled.",
                )
                return redirect("volunteer:volunteer_profile_detail", pk=pk)

            # Store team information before clearing for email notifications
            teams_before_cancel = list(profile.teams.all())

            # Update the volunteer profile
            profile.application_status = ApplicationStatus.CANCELLED
            profile.teams.clear()  # Remove from all teams
            profile.save()

            # Send confirmation email to volunteer
            from .models import _send_email

            context = {
                "profile": profile,
                "teams_removed": teams_before_cancel,
            }
            _send_email(
                subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Cancelled",
                recipient_list=[profile.user.email],
                html_template="volunteer/email/volunteer_cancellation_confirmation.html",
                text_template="volunteer/email/volunteer_cancellation_confirmation.txt",
                context=context,
            )

            # Send notification to team leads
            for team in teams_before_cancel:
                team_leads_emails = [lead.user.email for lead in team.team_leads.all()]
                if team_leads_emails:
                    context = {
                        "profile": profile,
                        "team": team,
                    }
                    _send_email(
                        subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Team Member Cancelled: {profile.user.get_full_name() or profile.user.username}",
                        recipient_list=team_leads_emails,
                        html_template="volunteer/email/team_lead_cancellation_notification.html",
                        text_template="volunteer/email/team_lead_cancellation_notification.txt",
                        context=context,
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

        except VolunteerProfile.DoesNotExist:
            messages.add_message(
                request, messages.ERROR, "Volunteer profile not found."
            )
            return redirect("volunteer:index")
        except Exception as e:
            messages.add_message(
                request, messages.ERROR, f"An error occurred while cancelling: {str(e)}"
            )
            return redirect("volunteer:volunteer_profile_detail", pk=pk)
