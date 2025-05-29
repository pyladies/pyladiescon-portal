from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView
from django.views.generic.edit import DeleteView, UpdateView

from .forms import SpeakerProfileForm
from .models import SpeakerProfile
# from .api.pretalx import fetch_event_speakers

# def pull_event_speakers(event_slug):
#     speaker_results = fetch_event_speakers()
#     print(speaker_results)
#     for speaker in speaker_results['results']:
#         print(speaker)
#     return speaker_results['results']


@login_required
def index(request):
    context = {}
    try:
        profile = SpeakerProfile.objects.first()
        if profile:
            context["profile_id"] = profile.id
    except SpeakerProfile.DoesNotExist:
        context["profile_id"] = None

    return render(request, "speaker/index.html", context)

class SpeakerProfileList(ListView):
    model = SpeakerProfile

class SpeakerProfileView(DetailView):
    model = SpeakerProfile

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object or self.object.name != request.name:
            return redirect("speaker:index")
        return super(SpeakerProfileView, self).get(request, *args, **kwargs)


###
# # CreateView does not need to Be Updated
###
# class SpeakerProfileCreate(CreateView):
#     model = SpeakerProfile
#     template_name = "speaker/speakerprofile_form.html"
#     success_url = reverse_lazy("speaker:index")
#     form_class = SpeakerProfileForm

#     def get(self, request, *args, **kwargs):
#         if SpeakerProfile.objects.filter(speaker__name=request.name).exists():
#             return redirect("speaker:index")
#         return super(SpeakerProfileCreate, self).get(request, *args, **kwargs)

#     def get_form_kwargs(self):
#         kwargs = super(SpeakerProfileCreate, self).get_form_kwargs()
#         kwargs.update({"name": self.request.name})
#         return kwargs


###
# # As of right now, if we allow Speakers to update their Profiles
# # Outside of pretalx, the data will diverge
###
class SpeakerProfileUpdate(UpdateView):
    model = SpeakerProfile
    template_name = "speaker/speakerprofile_form.html"
    success_url = reverse_lazy("speaker:index")
    form_class = SpeakerProfileForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object or self.object.name != request.name:
            return redirect("speaker:index")
        return super(SpeakerProfileUpdate, self).get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(SpeakerProfileUpdate, self).get_form_kwargs()
        kwargs.update({"name": self.request.name})
        return kwargs


class SpeakerProfileDelete(DeleteView):
    model = SpeakerProfile
    success_url = reverse_lazy("speaker:index")
