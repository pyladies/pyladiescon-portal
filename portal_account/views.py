from django.shortcuts import render

from django.views.generic import DetailView
from django.views.generic.edit import CreateView, UpdateView
from django.urls import reverse_lazy
from .models import PortalProfile
from .forms import PortalProfileForm


def index(request):
    context = {}
    if request.user.is_authenticated:
        try:
            profile = PortalProfile.objects.get(user=request.user)
            context["profile_id"] = profile.id
        except PortalProfile.DoesNotExist:
            context["profile_id"] = None
    return render(request, "portal_account/index.html", context)


class PortalProfileView(DetailView):
    model = PortalProfile


class PortalProfileCreate(CreateView):
    model = PortalProfile
    template_name = "portal_account/portalprofile_form.html"
    success_url = reverse_lazy("index")
    form_class = PortalProfileForm

    def get_form_kwargs(self):
        kwargs = super(PortalProfileCreate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class PortalProfileUpdate(UpdateView):
    model = PortalProfile
    fields = "__all__"
    success_url = reverse_lazy("index")
