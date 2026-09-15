from django.urls import path

from . import views

app_name = "speakers"

urlpatterns = [
    path("", views.SpeakerPortalIndexView.as_view(), name="index"),
    path(
        "invitations/<str:token>/",
        views.InvitationView.as_view(),
        name="invitation",
    ),
    path("sessions/", views.SessionListView.as_view(), name="session_list"),
    path("sessions/new/", views.SessionCreateView.as_view(), name="session_create"),
    path(
        "sessions/new-program-item/",
        views.ProgramItemCreateView.as_view(),
        name="program_item_create",
    ),
    path(
        "sessions/<int:pk>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "sessions/<int:pk>/edit/",
        views.SessionUpdateView.as_view(),
        name="session_edit",
    ),
]
