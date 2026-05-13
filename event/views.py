from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse

from .models import Event
from speaker.models import SpeakerProfile


###
# # Fetch Pretalx Speakers
###
from .api.pretalx import fetch_event_speakers

def pull_event_speakers(event_slug):
    speaker_results = fetch_event_speakers(event_slug)
    print(speaker_results)
    for speaker in speaker_results['results']:
        print(speaker)
    return speaker_results['results']

def create_speakers(speakers: list[dict]):
    for speaker in speakers:
        already_created = SpeakerProfile.objects.filter(code__contains=speaker.get('code'))
        if len(already_created) == 0:
            SpeakerProfile.objects.create(**speaker)
        else:
            print("Speaker already Created")
            print(already_created.first())

    print(SpeakerProfile.objects.count())


@login_required
def index(request):
    context = {}
    event = Event.objects.first()
    if event:
        context["event_slug"] = event.event_slug
    else:
        context["event_slug"] = None
    return render(request, "event/index.html", context)


@login_required
def load_speakers(request):
    # context = {}
    events = Event.objects.all()
    for event in events:
        pull_event_speakers(event.event_slug)
    return HttpResponse("")

