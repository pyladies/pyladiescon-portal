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
        "<int:pk>/",
        views.SponsorshipProfileDetail.as_view(),
        name="sponsorship_profile_detail",
    ),
    path(
        "<int:pk>/send-invoice/",
        views.SponsorshipProfileSendInvoice.as_view(),
        name="sponsorship_send_invoice",
    ),
]
