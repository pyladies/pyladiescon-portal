from allauth.account.views import EmailView, PasswordChangeView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, TemplateView
from django.views.generic.edit import CreateView, FormView, UpdateView

from common.mixins import MaintainerRequiredMixin

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
        form.save()
        messages.success(self.request, "Thank you. You are all set.")
        return redirect(self.request.POST.get("next") or "index")
