import django_filters
import django_tables2 as tables
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.views.generic.edit import CreateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from common.mixins import AdminRequiredMixin
from portal.common import get_sponsorships_stats_dict
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .forms import SponsorshipProfileForm
from .models import SponsorshipProfile, SponsorshipProgressStatus, SponsorshipTier


class CanViewSponsorship(UserPassesTestMixin):
    """Mixin for views that allows sponsorship listing.
    Open to approved volunteers.
    """

    def test_func(self):
        is_approved_volunteer = VolunteerProfile.objects.filter(
            user=self.request.user, application_status=ApplicationStatus.APPROVED
        ).exists()
        return (
            is_approved_volunteer
            or self.request.user.is_superuser
            or self.request.user.is_staff
        )


class SponsorshipProfileCreate(AdminRequiredMixin, CreateView):
    model = SponsorshipProfile
    template_name = "sponsorship/sponsorship_profile_form.html"
    success_url = reverse_lazy("sponsorship:sponsorship_list")
    form_class = SponsorshipProfileForm

    def get(self, request, *args, **kwargs):

        return super(SponsorshipProfileCreate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(SponsorshipProfileCreate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class SponsorshipProfileTable(tables.Table):

    creation_date = tables.Column(
        accessor="creation_date", verbose_name="Creation Date"
    )
    updated_date = tables.Column(accessor="modified_date", verbose_name="Last Updated")
    amount = tables.Column(accessor="sponsorship_tier__amount", verbose_name="Amount")
    actions = tables.Column(accessor="id", verbose_name="Actions")
    tier_name = tables.Column(
        accessor="sponsorship_tier__name", verbose_name="Sponsorship Tier"
    )

    class Meta:
        model = SponsorshipProfile
        fields = (
            "organization_name",
            "tier_name",
            "amount",
            "progress_status",
            "creation_date",
            "updated_date",
            # "actions",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_progress_status(self, value):
        """Render the progress status with a badge."""
        css_class = ""
        match value:
            case (
                SponsorshipProgressStatus.NOT_CONTACTED.label
                | SponsorshipProgressStatus.CANCELLED.label
            ):
                css_class = "bg-dark"
            case SponsorshipProgressStatus.REJECTED.label:
                css_class = "bg-danger"
            case (
                SponsorshipProgressStatus.ACCEPTED.label
                | SponsorshipProgressStatus.INVOICED.label
            ):
                css_class = "bg-info"
            case (
                SponsorshipProgressStatus.APPROVED.label
                | SponsorshipProgressStatus.PAID.label
            ):
                css_class = "bg-success"
            case (
                SponsorshipProgressStatus.AGREEMENT_SENT.label
                | SponsorshipProgressStatus.AGREEMENT_SIGNED.label
            ):
                css_class = "bg-primary"
            case SponsorshipProgressStatus.AWAITING_RESPONSE.label | _:
                css_class = "bg-warning"
        return format_html('<span class="badge {}">{}</span>', css_class, value)

    def render_amount(self, value, record):
        """Render the amount as currency."""
        if record.sponsorship_override_amount:
            amount = record.sponsorship_override_amount
        elif record.sponsorship_tier:
            amount = record.sponsorship_tier.amount
        else:
            amount = value
        return f"${amount:,.2f}" if amount else ""

    def render_actions(self, value, record):
        """Render action buttons for each sponsorship profile."""
        edit_url = reverse_lazy(
            "admin:sponsorship_sponsorshipprofile_change", args=[record.pk]
        )
        return format_html(
            '<a href="{}" class="btn btn-sm btn-primary me-1">Update</a>',
            edit_url,
        )


class SponsorshipProfileFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        label="Search by organization name", method="search_fulltext"
    )
    progress_status = django_filters.ChoiceFilter(
        method="filter_progress_status",
        choices=SponsorshipProgressStatus.choices,
        label="Progress Status",
        field_name="progress_status",
    )
    sponsorship_tier = django_filters.ModelChoiceFilter(
        queryset=SponsorshipTier.objects.all()
    )

    class Meta:
        model = SponsorshipProfile
        fields = ["search", "sponsorship_tier", "progress_status"]

    def search_fulltext(self, queryset, field_name, value):
        if not value:
            return queryset
        return queryset.annotate(  # pragma: no cover
            search=SearchVector("organization_name", "progress_status")
        ).filter(search=SearchQuery(value))

    def filter_progress_status(self, queryset, name, value):
        """Custom filtering for the progress_status field."""
        return queryset.filter(progress_status=value)

    @property
    def qs(self):
        queryset = super().qs
        if self.request.user.is_superuser:
            return queryset
        else:
            return queryset.filter(
                progress_status__in=[
                    SponsorshipProgressStatus.ACCEPTED,
                    SponsorshipProgressStatus.APPROVED,
                    SponsorshipProgressStatus.ACCEPTED,
                    SponsorshipProgressStatus.AGREEMENT_SENT,
                    SponsorshipProgressStatus.AGREEMENT_SIGNED,
                    SponsorshipProgressStatus.INVOICED,
                    SponsorshipProgressStatus.PAID,
                ]
            )


class SponsorshipProfileList(CanViewSponsorship, SingleTableMixin, FilterView):
    model = SponsorshipProfile
    template_name = "sponsorship/sponsorshipprofile_list.html"
    table_class = SponsorshipProfileTable
    filterset_class = SponsorshipProfileFilter

    def get_context_data(self, **kwargs):
        # kwargs.pop('filter')
        context = super().get_context_data(**kwargs)
        volunteer_profile = VolunteerProfile.objects.filter(
            user=self.request.user
        ).first()
        context["volunteer_profile"] = volunteer_profile
        context["title"] = "Sponsorship Profiles"
        context["stats"] = get_sponsorships_stats_dict()
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            context["table"].exclude = "actions"
        return context
