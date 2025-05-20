from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "speaker"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "list",
        login_required(views.SpeakerProfileList.as_view()),
        name="speaker_profile_list",
    ),
    path(
        "view/<int:pk>/",
        login_required(views.SpeakerProfileView.as_view()),
        name="speaker_profile_detail",
    ),
    path(
        "new",
        login_required(views.SpeakerProfileCreate.as_view()),
        name="speaker_profile_new",
    ),
    path(
        "edit/<int:pk>",
        login_required(views.SpeakerProfileUpdate.as_view()),
        name="speaker_profile_edit",
    ),
    path(
        "delete/<int:pk>",
        views.SpeakerProfileDelete.as_view(),
        name="speaker_profile_delete",
    ),
]
