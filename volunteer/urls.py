from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "volunteer"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "list",
        login_required(views.VolunteerProfileList.as_view()),
        name="volunteer_profile_list",
    ),
    path(
        "view/<int:pk>/",
        login_required(views.VolunteerProfileView.as_view()),
        name="volunteer_profile_detail",
    ),
    path(
        "new",
        login_required(views.VolunteerProfileCreate.as_view()),
        name="volunteer_profile_new",
    ),
    path(
        "edit/<int:pk>",
        login_required(views.VolunteerProfileUpdate.as_view()),
        name="volunteer_profile_edit",
    ),
    path(
        "delete/<int:pk>",
        views.VolunteerProfileDelete.as_view(),
        name="volunteer_profile_delete",
    ),
    path(
        "list",
        login_required(views.VolunteerProfileList.as_view()),
        name="volunteers_list",
    ),
    path(
        "volunteer_profile_manage/<int:pk>/",
        views.ManageVolunteerProfile.as_view(),
        name="volunteer_profile_manage",
    ),
    path(
        "resend_onboarding_email/<int:pk>/",
        views.ResendOnboardingEmailView.as_view(),
        name="resend_onboarding_email",
    ),
    path(
        "cancel/<int:pk>/",
        login_required(views.CancelVolunteeringView.as_view()),
        name="cancel_volunteering",
    ),
]
