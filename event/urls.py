from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "speaker"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "load-speakers",
        login_required(views.load_speakers),
        name="speaker-load",
    ),
]
