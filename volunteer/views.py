from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .forms import VolunteerProfileForm
from .models import Team, VolunteerProfile


@login_required
def index(request):
    context = {}
    try:
        profile = VolunteerProfile.objects.get(user=request.user)
        context["profile_id"] = profile.id
    except VolunteerProfile.DoesNotExist:
        context["profile_id"] = None
    return render(request, "volunteer/index.html", context)


class VolunteerProfileList(ListView):
    model = VolunteerProfile


class VolunteerProfileView(DetailView):
    model = VolunteerProfile

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object or self.object.user != request.user:
            return redirect("volunteer:index")
        return super(VolunteerProfileView, self).get(request, *args, **kwargs)


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

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object:
            return redirect("teams")
        return super(TeamView, self).get(request, *args, **kwargs)
