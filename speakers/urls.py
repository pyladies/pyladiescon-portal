from django.urls import path

from . import views

app_name = "speakers"

urlpatterns = [
    path("", views.SpeakerPortalIndexView.as_view(), name="index"),
]
