from django.urls import path

from . import views
from .views import SponsorshipProfileListView

app_name = "sponsorship"

urlpatterns = [
    path(
        "create/", views.create_sponsorship_profile, name="create_sponsorship_profile"
    ),
    path(
        "list/", SponsorshipProfileListView.as_view(), name="sponsorship_profile_list"
    ),
]
