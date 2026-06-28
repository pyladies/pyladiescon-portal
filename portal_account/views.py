from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView
from django.views.generic.edit import CreateView, UpdateView

from .forms import PortalProfileForm
from .models import PortalProfile


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


class PortalProfileUpdate(UpdateView):
    model = PortalProfile
    template_name = "portal_account/portalprofile_form.html"
    success_url = reverse_lazy("index")
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
