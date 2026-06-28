import django_filters
import django_tables2 as tables
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.views.generic import DetailView, ListView
from django.views.generic.base import View
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from common.mixins import AdminRequiredMixin
from portal.common import get_sponsorships_stats_dict
from portal.models import Conference
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .emails import send_psf_invoice_request_email
from .forms import SponsorshipProfileForm, SponsorshipTierForm
from .models import SponsorshipProfile, SponsorshipProgressStatus, SponsorshipTier


class CanViewSponsorship(UserPassesTestMixin):
    """Mixin for views that allow sponsorship viewing.

    Staff and superusers may view every conference. Other users may only view
    the conferences they were an approved volunteer for — they see the year(s)
    they are approved for.
    """

    def viewable_conferences(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return Conference.objects.all()
        return Conference.objects.filter(
            volunteer_profiles__user=user,
            volunteer_profiles__application_status=ApplicationStatus.APPROVED,
        ).distinct()

    def test_func(self):
        return self.viewable_conferences().exists()


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


class SponsorshipProfileUpdate(AdminRequiredMixin, UpdateView):
    model = SponsorshipProfile
    template_name = "sponsorship/sponsorship_profile_form.html"
    form_class = SponsorshipProfileForm

    # No ``user`` kwarg passed to the form: editing must not reassign the owner.

    def get_success_url(self):
        return reverse_lazy(
            "sponsorship:sponsorship_profile_detail", kwargs={"pk": self.object.pk}
        )


class SponsorshipProfileDelete(AdminRequiredMixin, DeleteView):
    model = SponsorshipProfile
    template_name = "sponsorship/sponsorship_profile_confirm_delete.html"
    context_object_name = "profile"
    success_url = reverse_lazy("sponsorship:sponsorship_list")


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
    logo = tables.Column(accessor="logo", verbose_name="Logo")
    github_issue_url = tables.Column(
        accessor="github_issue_url", verbose_name="GitHub Issue"
    )

    class Meta:
        model = SponsorshipProfile
        fields = (
            "organization_name",
            "logo",
            "tier_name",
            "amount",
            "progress_status",
            "github_issue_url",
            "creation_date",
            "updated_date",
            "actions",
        )
        attrs = {
            "class": "table table-hover table-bordered table-sm",
            "thead": {"class": "table-light"},
        }

    def render_organization_name(self, value, record):
        """Render the organization name as a link to the detail view."""
        detail_url = reverse_lazy(
            "sponsorship:sponsorship_profile_detail", args=[record.pk]
        )
        return format_html('<a href="{}">{}</a>', detail_url, value)

    def render_logo(self, value, record):
        """Render the logo as a small image with link to the full image."""
        if value:
            return format_html(
                '<a href="{value}"><img src="{value}" alt="Logo of {name}" class="img-fluid" width="100" height="100"></a>',
                value=value.url,
                name=record.organization_name,
            )
        else:
            return ""

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
            "sponsorship:sponsorship_profile_edit", args=[record.pk]
        )
        delete_url = reverse_lazy(
            "sponsorship:sponsorship_profile_delete", args=[record.pk]
        )
        # Icon-only in the table (tooltip + aria-label for accessibility).
        return format_html(
            '<a href="{}" class="btn btn-sm btn-primary" title="Edit" '
            'aria-label="Edit"><i class="fa-solid fa-pencil"></i></a> '
            '<a href="{}" class="btn btn-sm btn-outline-danger" title="Delete" '
            'aria-label="Delete"><i class="fa-solid fa-trash"></i></a>',
            edit_url,
            delete_url,
        )

    def render_github_issue_url(self, value, record):
        """Render the GitHub Issue URL if exists."""
        if value:
            return format_html(
                '<a href="{}" target="_blank"><i class="fa-brands fa-github"></i></a>',
                value,
            )
        else:
            return ""


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
        queryset=SponsorshipTier.objects.none()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tiers are per-edition, so the dropdown should only offer the tiers of
        # the conference being viewed (matching the conference-scoped list),
        # not every year's tiers.
        param = self.request.GET.get("conference") if self.request else None
        conference = None
        if param:
            conference = Conference.objects.filter(pk=param).first()
        if conference is None:
            conference = Conference.get_active()
        self.filters["sponsorship_tier"].queryset = SponsorshipTier.objects.filter(
            conference=conference
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

    def get_selected_conference(self):
        """The conference whose sponsors are shown.

        Defaults to the active conference when the viewer may see it, otherwise
        their most recent viewable year. ``?conference=<pk>`` switches years but
        only among the conferences the viewer is allowed to see.
        """
        viewable = self.viewable_conferences()
        param = self.request.GET.get("conference")
        if param:
            return viewable.filter(pk=param).first()
        active = Conference.get_active()
        if active is not None and viewable.filter(pk=active.pk).exists():
            return active
        return viewable.order_by("-year").first()

    def get_queryset(self):
        # ``conference=None`` matches nothing, so a year the viewer may not see
        # yields an empty list rather than leaking another year's sponsors.
        return super().get_queryset().filter(conference=self.get_selected_conference())

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        user = self.request.user
        # Read-only viewers (approved volunteers, not staff) can't edit or
        # delete, so drop the actions column instead of showing buttons that 403.
        if not (user.is_superuser or user.is_staff):
            kwargs["exclude"] = ("actions",)
        return kwargs

    def get_context_data(self, **kwargs):
        # kwargs.pop('filter')
        context = super().get_context_data(**kwargs)
        selected_conference = self.get_selected_conference()
        volunteer_profile = VolunteerProfile.objects.filter(
            user=self.request.user, conference=Conference.get_active()
        ).first()
        context["volunteer_profile"] = volunteer_profile
        context["title"] = "Sponsorship Profiles"
        # Stats follow the selected year tab so the overview matches the list.
        context["stats"] = (
            get_sponsorships_stats_dict(selected_conference)
            if selected_conference
            else None
        )
        context["conferences"] = self.viewable_conferences()
        context["selected_conference"] = selected_conference
        return context


class SponsorshipProfileDetail(CanViewSponsorship, DetailView):
    model = SponsorshipProfile
    template_name = "sponsorship/sponsorship_profile_detail.html"
    context_object_name = "profile"

    def test_func(self):
        # A viewer may open a sponsor only if they may see that sponsor's year.
        return (
            self.viewable_conferences()
            .filter(pk=self.get_object().conference_id)
            .exists()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_send_invoice"] = (
            self.request.user.is_superuser or self.request.user.is_staff
        ) and self.object.progress_status == SponsorshipProgressStatus.APPROVED
        return context


class SponsorshipProfileSendInvoice(AdminRequiredMixin, View):
    def post(self, request, pk):
        profile = get_object_or_404(SponsorshipProfile, pk=pk)

        # Send email to PSF accounting team
        send_psf_invoice_request_email(profile)

        messages.success(
            request,
            f"Invoice request sent to PSF accounting team for {profile.organization_name}",
        )

        return redirect("sponsorship:sponsorship_profile_detail", pk=pk)


class SponsorshipTierList(AdminRequiredMixin, ListView):
    model = SponsorshipTier
    template_name = "sponsorship/sponsorshiptier_list.html"
    context_object_name = "tiers"

    def get_selected_conference(self):
        """The edition whose tiers are shown; ``?conference=<pk>`` switches it."""
        param = self.request.GET.get("conference")
        if param:
            conference = Conference.objects.filter(pk=param).first()
            if conference is not None:
                return conference
        return Conference.get_active()

    def get_queryset(self):
        return SponsorshipTier.objects.filter(
            conference=self.get_selected_conference()
        ).order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conferences"] = Conference.objects.all()
        context["selected_conference"] = self.get_selected_conference()
        return context


class SponsorshipTierCreate(AdminRequiredMixin, CreateView):
    model = SponsorshipTier
    form_class = SponsorshipTierForm
    template_name = "sponsorship/sponsorshiptier_form.html"
    success_url = reverse_lazy("sponsorship:tier_list")


class SponsorshipTierUpdate(AdminRequiredMixin, UpdateView):
    model = SponsorshipTier
    form_class = SponsorshipTierForm
    template_name = "sponsorship/sponsorshiptier_form.html"
    success_url = reverse_lazy("sponsorship:tier_list")


class SponsorshipTierDelete(AdminRequiredMixin, DeleteView):
    model = SponsorshipTier
    template_name = "sponsorship/sponsorshiptier_confirm_delete.html"
    context_object_name = "tier"
    success_url = reverse_lazy("sponsorship:tier_list")
