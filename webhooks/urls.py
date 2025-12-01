from django.urls import path

from . import views

app_name = "webhooks"

urlpatterns = [
    path(
        "pretix/",
        views.pretix_webhook,
        name="pretix_webhook",
    ),
]
