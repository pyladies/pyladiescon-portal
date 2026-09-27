from allauth.account.views import EmailView, PasswordChangeView
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, FormView, UpdateView
from django_filters.views import FilterView

from common.mixins import MaintainerRequiredMixin
from common.models import SentEmail, kind_of

from .filters import SentEmailFilter
from .forms import PortalProfileForm
from .forms_agreements import AgreementsForm
from .models import PortalProfile
from .stats import DAILY_RANGES, DEFAULT_DAILY_RANGE, account_signup_stats


@login_required
def index(request):
    # Pass the whole profile (not just its id) so the account page can render
    # the identity summary inline instead of sending the user to a separate
    # detail page.
    profile = PortalProfile.objects.filter(user=request.user).first()
    return render(request, "portal_account/index.html", {"profile": profile})


class PortalProfileView(DetailView):
    model = PortalProfile

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object or self.object.user != request.user:
            return redirect("portal_account:index")
        return super(PortalProfileView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Account settings rail (Stage E).
        context["profile"] = self.object
        context["account_active"] = "profile_view"
        return context


class PortalProfileCreate(CreateView):
    model = PortalProfile
    template_name = "portal_account/portalprofile_form.html"
    success_url = reverse_lazy("index")
    form_class = PortalProfileForm

    def get(self, request, *args, **kwargs):
        if PortalProfile.objects.filter(user__id=request.user.id).exists():
            return redirect("portal_account:index")
        return super(PortalProfileCreate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(PortalProfileCreate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # No profile yet, so the rail offers "Create my profile" (Stage E).
        context["profile"] = None
        context["account_active"] = "profile_new"
        return context


class PortalProfileUpdate(UpdateView):
    model = PortalProfile
    template_name = "portal_account/portalprofile_form.html"
    # Editing returns to the account page (the hub), not the landing page.
    success_url = reverse_lazy("portal_account:index")
    form_class = PortalProfileForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object or self.object.user != request.user:
            return redirect("portal_account:index")
        return super(PortalProfileUpdate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(PortalProfileUpdate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Account settings rail (Stage E).
        context["profile"] = self.object
        context["account_active"] = "profile_edit"
        return context


class AccountEmailView(EmailView):
    """allauth email management that returns to the account page when done."""

    success_url = reverse_lazy("portal_account:index")


class AccountPasswordChangeView(PasswordChangeView):
    """allauth password change that returns to the account page when done."""

    success_url = reverse_lazy("portal_account:index")


class MaintenanceAccountsView(MaintainerRequiredMixin, TemplateView):
    """Maintenance > Accounts: signup volume and verification, at a glance.

    Read-only and computed on request. This is the page that would have shown
    the 2026 signup flood in its first week; see
    docs/architecture/signup-abuse-protection.md.
    """

    template_name = "portal_account/maintenance_accounts.html"

    def get_days(self):
        try:
            days = int(self.request.GET.get("days", DEFAULT_DAILY_RANGE))
        except ValueError:
            return DEFAULT_DAILY_RANGE
        return days if days in DAILY_RANGES else DEFAULT_DAILY_RANGE

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = self.get_days()
        context.update(account_signup_stats(days))
        context["daily_ranges"] = DAILY_RANGES
        # One axis label a week on the 30-day view, one a fortnight on 90.
        context["label_every"] = 7 if days <= 31 else 15
        return context


class MaintenanceEmailsView(MaintainerRequiredMixin, FilterView):
    """Maintenance > Emails: the record of every email the portal sent.

    Maintainer-only because it holds message bodies for everyone. Newest
    first, filtered by edition, presenter, kind and outcome, searched by
    subject or address; a row expands to the body. Reading is the point:
    there is no resend, which is a different decision with its own consent
    questions (design §13.1).
    """

    template_name = "portal_account/maintenance_emails.html"
    filterset_class = SentEmailFilter
    paginate_by = 50

    def get_queryset(self):
        return SentEmail.objects.select_related(
            "conference", "user", "presenter", "session"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["retention_days"] = settings.EMAIL_RECORD_RETENTION_DAYS
        return context


class MyEmailsView(LoginRequiredMixin, ListView):
    """Manage account > Emails we sent you.

    Exactly the records that are theirs by ``SentEmailQuerySet.owned_by``:
    sent to their account, or to a presenter row their account is linked
    to, which is how a speaker sees the invitation that arrived before they
    had an account. No filter beyond the kind; a person's own trail is short.
    """

    template_name = "portal_account/my_emails.html"
    paginate_by = 50

    def get_queryset(self):
        queryset = SentEmail.objects.owned_by(self.request.user).select_related(
            "conference", "session"
        )
        kind = self.request.GET.get("kind")
        if kind:
            queryset = queryset.filter(template=kind)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = (
            SentEmail.objects.owned_by(self.request.user)
            .order_by("template")
            .values_list("template", flat=True)
            .distinct()
        )
        context.update(
            {
                "profile": PortalProfile.objects.filter(user=self.request.user).first(),
                "account_active": "emails",
                "retention_days": settings.EMAIL_RECORD_RETENTION_DAYS,
                "kinds": [(template, kind_of(template)) for template in templates],
                "kind": self.request.GET.get("kind", ""),
            }
        )
        return context


class AgreementsView(LoginRequiredMixin, FormView):
    """Ask for the Code of Conduct and Terms of Service.

    The gate (``portal_account.agreements``) sends any signed-in account here
    that has not accepted both, whatever route it arrived by: signup collects
    them, a speaker invitation and a sign-in code do not.
    """

    template_name = "portal_account/agreements.html"
    form_class = AgreementsForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        profile = form.save()
        user = self.request.user
        if not user.get_full_name().strip():
            # Creating the profile here means the portal index no longer
            # sends them to fill it in, so ask for the name now. An account
            # made outside signup has none.
            messages.info(
                self.request, "Thank you. One more thing: your name, for your badge."
            )
            return redirect("portal_account:portal_profile_edit", pk=profile.pk)
        messages.success(self.request, "Thank you. You are all set.")
        return redirect(self.request.POST.get("next") or "index")
