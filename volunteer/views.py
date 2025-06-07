import django_tables2 as tables
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django_filters import CharFilter, FilterSet
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from .forms import VolunteerProfileForm, VolunteerProfileReviewForm
from .models import ApplicationStatus, Team, VolunteerProfile


@login_required
def index(request):
    context = {}
    try:
        profile = VolunteerProfile.objects.get(user=request.user)
        context["profile_id"] = profile.id
    except VolunteerProfile.DoesNotExist:
        context["profile_id"] = None
    return render(request, "volunteer/index.html", context)


class VolunteerAdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require administrative permission for the volunteers.
    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff


class VolunteerProfileFilter(FilterSet):
    search = CharFilter(
        label="Search by username, first name, or last name", method="search_fulltext"
    )

    class Meta:
        model = VolunteerProfile
        fields = ["search"]

    def search_fulltext(self, queryset, field_name, value):
        if not value:
            return queryset
        return queryset.annotate(  # pragma: no cover
            search=SearchVector("user__username")
        ).filter(search=SearchQuery(value))


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
        """Render the actions column with link to review the application."""
        render_html = ""
        if record.application_status == ApplicationStatus.PENDING:
            review_url = reverse(
                "volunteer:volunteer_profile_review", kwargs={"pk": record.pk}
            )
            render_html = format_html(
                '<a href="{}" class="btn btn-sm btn-primary">Review</a> ', review_url
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
        """Render the teams as badges."""
        html_content = ""
        for team in record.teams.all():
            html_content = format_html(
                '{}<span class="badge bg-secondary">{}</span> ',
                html_content,
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


class VolunteerProfileView(DetailView):
    model = VolunteerProfile

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if (
            not self.object
            or self.object.user != request.user
            and not request.user.is_staff
        ):
            return redirect("volunteer:index")
        return super(VolunteerProfileView, self).get(request, *args, **kwargs)


class ReviewVolunteerProfileView(VolunteerAdminRequiredMixin, UpdateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_review_form.html"
    success_url = reverse_lazy("volunteer:volunteer_profile_list")
    form_class = VolunteerProfileReviewForm

    def get_form_kwargs(self):
        kwargs = super(ReviewVolunteerProfileView, self).get_form_kwargs()
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
        self.object = self.get_object()
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


class TeamList(LoginRequiredMixin, ListView):
    model = Team
    template_name = "team/index.html"
    context_object_name = "teams"


class TeamView(LoginRequiredMixin, DetailView):
    model = Team
    template_name = "team/team_detail.html"
    context_object_name = "team"

    def get(self, request, pk):
        try:
            self.object = Team.objects.get(pk=pk)
        except Team.DoesNotExist:
            return redirect("teams")
        return super(TeamView, self).get(request, pk)
