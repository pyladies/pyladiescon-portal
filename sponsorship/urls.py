from django.urls import path

from . import views

app_name = "sponsorship"

urlpatterns = [
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
