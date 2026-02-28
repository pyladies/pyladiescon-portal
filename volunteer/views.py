import django_filters
import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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

from common.mixins import AdminRequiredMixin, VolunteerOrAdminRequiredMixin

from .forms import VolunteerProfileForm, VolunteerProfileReviewForm
from .models import (
    ApplicationStatus,
    PyladiesChapter,
    Team,
    VolunteerProfile,
    send_volunteer_cancelled_emails,
    send_volunteer_onboarding_email,
)

# ------------------- Volunteer Index -------------------
@login_required
def index(request):
    context = {}
    try:
        profile = VolunteerProfile.objects.get(user=request.user)
        context["profile"] = profile
    except VolunteerProfile.DoesNotExist:
        context["profile"] = None
    return render(request, "volunteer/index.html", context)

# ------------------- Mixins -------------------
class VolunteerAdminRequiredMixin(AdminRequiredMixin):
    """Mixin for views that require administrative permission for volunteers."""

# ------------------- Filters -------------------
class VolunteerProfileFilter(django_filters.FilterSet):

    search = django_filters.CharFilter(
        label="Search by username, first name, or last name", method="search_fulltext"
    )

    class Meta:
        model = VolunteerProfile
        fields = ["search", "application_status"]

    def search_fulltext(self, queryset, field_name, value):
        if not value:
            return queryset
        return queryset.annotate(
            search=SearchVector("user__username", "user__first_name", "user__last_name")
        ).filter(SearchQuery(value))

# ------------------- Tables -------------------
class VolunteerProfileTable(tables.Table):

    date_joined = tables.Column(accessor="user__date_joined", verbose_name="Joined Date")
    application_date = tables.Column(accessor="creation_date", verbose_name="Application Date")
    updated_date = tables.Column(accessor="modified_date", verbose_name="Application Last Updated")
    discord_username = tables.Column(accessor="discord_username", verbose_name="Discord Username")
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
        if value == ApplicationStatus.APPROVED:
            return format_html('<span class="badge bg-success">{}</span>', value)
        elif value == ApplicationStatus.REJECTED:
            return format_html('<span class="badge bg-danger">{}</span>', value)
        elif value == ApplicationStatus.CANCELLED:
            return format_html('<span class="badge bg-secondary">{}</span>', value)
        else:
            return format_html('<span class="badge bg-warning">{}</span>', value)

    def render_actions(self, value, record):
        render_html = ""
        application_status = record.application_status
        url = reverse("volunteer:volunteer_profile_manage", kwargs={"pk": record.pk})
        if application_status in [ApplicationStatus.PENDING, ApplicationStatus.WAITLISTED]:
            render_html = format_html('<a href="{}" class="btn btn-sm btn-primary">Review</a> ', url)
        elif application_status == ApplicationStatus.APPROVED:
            render_html = format_html('<a href="{}" class="btn btn-sm btn-info">Manage</a> ', url)
        return render_html

    def render_username(self, value, record):
        detail_url = reverse("volunteer:volunteer_profile_detail", kwargs={"pk": record.pk})
        html_content = format_html('<a href="{}">{}</a>', detail_url, record.user.username)
        if record.user.is_superuser:
            html_content = format_html('{} <i class="fa-solid fa-user-secret"></i>', html_content)
        return html_content

    def render_teams(self, value, record):
        html_content = ""
        for team in record.teams.all():
            team_url = reverse("team_detail", kwargs={"pk": team.pk})
            html_content = format_html('{}<a href="{}" class="badge bg-secondary">{}</a> ', html_content, team_url, team.short_name)
        return html_content

    def render_roles(self, value, record):
        html_content = ""
        for role in record.roles.all():
            html_content = format_html('{}<span class="badge bg-secondary">{}</span> ', html_content, role.short_name)
        return html_content

# ------------------- Views -------------------
class VolunteerProfileList(VolunteerAdminRequiredMixin, SingleTableMixin, FilterView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_list.html"
    table_class = VolunteerProfileTable
    filterset_class = VolunteerProfileFilter

class VolunteerProfileView(DetailView):
    model = VolunteerProfile

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except Http404:
            return redirect("volunteer:index")
        if not self.object or self.object.user != request.user and not request.user.is_staff:
            return redirect("volunteer:index")
        return super().get(request, *args, **kwargs)

class ManageVolunteerProfile(VolunteerAdminRequiredMixin, UpdateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_review_form.html"
    success_url = reverse_lazy("volunteer:volunteer_profile_list")
    form_class = VolunteerProfileReviewForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
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
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
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
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
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
        return super().get(request, pk)

class ResendOnboardingEmailView(VolunteerAdminRequiredMixin, View):

    def post(self, request, pk):
        try:
            profile = VolunteerProfile.objects.get(pk=pk)
            if profile.application_status == ApplicationStatus.APPROVED:
                send_volunteer_onboarding_email(profile)
                messages.add_message(request, messages.SUCCESS, "Onboarding email was sent successfully.")
            else:
                messages.add_message(request, messages.ERROR, "Onboarding email can only be sent to approved volunteers.")
        except VolunteerProfile.DoesNotExist:
            messages.add_message(request, messages.ERROR, "Volunteer profile not found.")
        except Exception as e:
            messages.add_message(request, messages.ERROR, f"An error occurred: {str(e)}")
        return redirect("volunteer:volunteer_profile_manage", pk=pk)

class CancelVolunteeringView(VolunteerOrAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            profile = VolunteerProfile.objects.get(pk=pk)
            if profile.application_status == ApplicationStatus.CANCELLED:
                messages.add_message(request, messages.WARNING, "This volunteer application is already cancelled.")
                return redirect("volunteer:volunteer_profile_detail", pk=pk)

            teams_before_cancel = list(profile.teams.all())
            roles_before_cancel = list(profile.roles.all())
            profile.application_status = ApplicationStatus.CANCELLED
            profile.teams.clear()
            profile.roles.clear()
            profile.save()

            send_volunteer_cancelled_emails(profile, teams_before_cancel, roles_before_cancel)
            messages.add_message(request, messages.SUCCESS, "Your volunteer application has been cancelled successfully.")

            if request.user.is_staff or request.user.is_superuser:
                return redirect("volunteer:volunteer_profile_list")
            else:
                return redirect("volunteer:index")
        except Exception as e:
            messages.add_message(request, messages.ERROR, f"An error occurred while cancelling: {str(e)}")
            return redirect("volunteer:volunteer_profile_detail", pk=pk)

class PyladiesChaptersList(ListView):
    model = PyladiesChapter
    template_name = "pyladies_chapter/index.html"
    context_object_name = "pyladies_chapters"

# ------------------- GeoCharts Dashboard -------------------
@login_required
def volunteer_geo_dashboard(request):
    """Dashboard view to show volunteer locations using GeoCharts."""
    volunteers = VolunteerProfile.objects.all()
    
    geo_data = {}
    for v in volunteers:
        country = getattr(v, "country", None)  # Replace with your actual country field
        if country:
            geo_data[country] = geo_data.get(country, 0) + 1

    return render(request, "volunteer/geo_dashboard.html", {"geo_data": geo_data})