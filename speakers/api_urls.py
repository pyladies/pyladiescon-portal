from django.urls import path

from . import api_views

app_name = "speakers_api"

urlpatterns = [
    path(
        "<slug:conference>/sessions/",
        api_views.SessionsApiView.as_view(),
        name="sessions",
    ),
    path(
        "<slug:conference>/sessions/<slug:slug>.ics",
        api_views.ApiSessionFeedView.as_view(),
        name="session_ics",
    ),
    path(
        "<slug:conference>/sessions/<slug:slug>/",
        api_views.SessionApiView.as_view(),
        name="session",
    ),
    path(
        "<slug:conference>/presenters/",
        api_views.PresentersApiView.as_view(),
        name="presenters",
    ),
    path(
        "<slug:conference>/schedule/",
        api_views.ScheduleApiView.as_view(),
        name="schedule",
    ),
    path(
        "<slug:conference>/schedule.ics",
        api_views.ApiScheduleFeedView.as_view(),
        name="schedule_ics",
    ),
]
