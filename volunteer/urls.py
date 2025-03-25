from django.urls import path

from . import views

app_name = "volunteer"

urlpatterns = [
    path("", views.index, name="index"),
    path("list", views.VolunteerProfileList.as_view(), name="volunteer_profile_list"),
    path(
        "view/<int:pk>/",
        views.VolunteerProfileView.as_view(),
        name="volunteer_profile_detail",
    ),
    path("new", views.VolunteerProfileCreate.as_view(), name="volunteer_profile_new"),
    path(
        "edit/<int:pk>",
        views.VolunteerProfileUpdate.as_view(),
        name="volunteer_profile_edit",
    ),
    path(
        "delete/<int:pk>",
        views.VolunteerProfileDelete.as_view(),
        name="volunteer_profile_delete",
    ),
]
