from django.urls import path
from . import views

app_name = "sponsorship"

urlpatterns = [
    path("profile/", views.sponsorship_profile_create, name="profile_create"),
]
