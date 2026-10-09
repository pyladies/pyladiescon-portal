from django.urls import path

from . import embed_views

app_name = "speakers_embed"

urlpatterns = [
    path(
        "<slug:conference>/<slug:view>/",
        embed_views.EmbedView.as_view(),
        name="embed",
    ),
]
