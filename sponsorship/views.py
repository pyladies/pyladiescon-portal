import django_filters
import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.shortcuts import render
from django.utils.html import format_html
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from .forms import SponsorshipProfileForm
from .models import SponsorshipProfile


@login_required
def create_sponsorship_profile(request):
    if request.method == "POST":
        form = SponsorshipProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.application_status = "pending"
            profile.save()
            form.save_m2m()  # Save ManyToMany relationships
            messages.success(request, "Sponsorship profile submitted successfully!")
            form = SponsorshipProfileForm()  # Clear form after submission
    else:
        form = SponsorshipProfileForm()
    return render(request, "sponsorship/sponsorship_profile_form.html", {"form": form})


class SponsorshipAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff


class SponsorshipProfileTable(tables.Table):
    organization_name = tables.Column(verbose_name="Organization")
    main_contact_user = tables.Column(
        accessor="main_contact_user", verbose_name="Main Contact"
    )
    sponsorship_type = tables.Column(verbose_name="Type")
    # sponsorship_tier = tables.Column(verbose_name="Tier")
    company_description = tables.Column(verbose_name="Company Description")
    application_status = tables.Column(verbose_name="Application Status")

    class Meta:
        model = SponsorshipProfile
        fields = (
            "organization_name",
            "main_contact_user",
            "sponsorship_type",
            "company_description",
            "application_status",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_main_contact_user(self, value):
        return format_html("<b>{}</b>", value)

    def render_application_status(self, value):
        return format_html('<span class="badge bg-info">{}</span>', value)


class SponsorshipProfileFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        label="Search by organization or contact", method="search_fulltext"
    )
    sponsorship_type = django_filters.ChoiceFilter(
        choices=SponsorshipProfile.SPONSORSHIP_TYPES, label="Sponsorship Type"
    )
    application_status = django_filters.ChoiceFilter(
        choices=SponsorshipProfile.APPLICATION_STATUS_CHOICES,
        label="Application Status",
    )

    class Meta:
        model = SponsorshipProfile
        fields = ["search", "sponsorship_type", "application_status"]

    def search_fulltext(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.annotate(
            search=SearchVector("organization_name", "main_contact_user__username")
        ).filter(search=SearchQuery(value))


class SponsorshipProfileListView(
    LoginRequiredMixin, SponsorshipAdminRequiredMixin, SingleTableMixin, FilterView
):
    model = SponsorshipProfile
    table_class = SponsorshipProfileTable
    template_name = "sponsorship/sponsorshipprofile_list.html"
    filterset_class = SponsorshipProfileFilter
    context_object_name = "sponsors"
