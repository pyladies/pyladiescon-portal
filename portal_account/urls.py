from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "volunteer"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "profile/view/<int:pk>/",
        login_required(views.PortalProfileView.as_view()),
        name="portal_profile_detail",
    ),
    path(
        "profile/new",
        login_required(views.PortalProfileCreate.as_view()),
        name="portal_profile_new",
    ),
    path(
        "profile/edit/<int:pk>",
        login_required(views.PortalProfileUpdate.as_view()),
        name="portal_profile_edit",
    ),
]
