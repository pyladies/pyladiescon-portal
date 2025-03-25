from django.shortcuts import render
from django.views.generic import ListView, DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy

from .models import VolunteerProfile
from .forms import VolunteerProfileForm


def index(request):
    context = {}
    if request.user.is_authenticated:
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


class VolunteerProfileCreate(CreateView):
    model = VolunteerProfile
    template_name = "volunteer/volunteerprofile_form.html"
    success_url = reverse_lazy("volunteer:index")
    form_class = VolunteerProfileForm

    def get_form_kwargs(self):
        kwargs = super(VolunteerProfileCreate, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs


class VolunteerProfileUpdate(UpdateView):
    model = VolunteerProfile
    fields = "__all__"
    success_url = reverse_lazy("volunteer:index")


class VolunteerProfileDelete(DeleteView):
    model = VolunteerProfile
    success_url = reverse_lazy("volunteer:index")
