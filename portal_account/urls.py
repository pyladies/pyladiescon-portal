from django.urls import path

from . import views

app_name = "volunteer"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "profile/view/<int:pk>/",
        views.PortalProfileView.as_view(),
        name="portal_profile_detail",
    ),
    path("profile/new", views.PortalProfileCreate.as_view(), name="portal_profile_new"),
    path(
        "profile/edit/<int:pk>",
        views.PortalProfileUpdate.as_view(),
        name="portal_profile_edit",
    ),
]
