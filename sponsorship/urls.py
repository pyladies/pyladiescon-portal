from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "sponsorship"

urlpatterns = [
    # The list (which carries the stats header) is the sponsorship home. Make the
    # bare /sponsorship/ resolve to it instead of 404-ing.
    path(
        "",
        RedirectView.as_view(pattern_name="sponsorship:sponsorship_list"),
        name="index",
    ),
    path(
        "new",
        views.SponsorshipProfileCreate.as_view(),
        name="sponsorship_profile_new",
    ),
    path(
        "list",
        views.SponsorshipProfileList.as_view(),
        name="sponsorship_list",
    ),
    path(
        "tiers/",
        views.SponsorshipTierList.as_view(),
        name="tier_list",
    ),
    path(
        "tiers/new/",
        views.SponsorshipTierCreate.as_view(),
        name="tier_new",
    ),
    path(
        "tiers/<int:pk>/edit/",
        views.SponsorshipTierUpdate.as_view(),
        name="tier_edit",
    ),
    path(
        "tiers/<int:pk>/delete/",
        views.SponsorshipTierDelete.as_view(),
        name="tier_delete",
    ),
    path(
        "<int:pk>/",
        views.SponsorshipProfileDetail.as_view(),
        name="sponsorship_profile_detail",
    ),
    path(
        "<int:pk>/edit/",
        views.SponsorshipProfileUpdate.as_view(),
        name="sponsorship_profile_edit",
    ),
    path(
        "<int:pk>/delete/",
        views.SponsorshipProfileDelete.as_view(),
        name="sponsorship_profile_delete",
    ),
    path(
        "<int:pk>/send-invoice/",
        views.SponsorshipProfileSendInvoice.as_view(),
        name="sponsorship_send_invoice",
    ),
]
