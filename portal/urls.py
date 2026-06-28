"""
URL configuration for portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from portal import views
from portal_account import views as portal_account_views
from volunteer import views as volunteer_view

urlpatterns = [
    path("", views.index, name="index"),
    path("volunteer/", include("volunteer.urls", namespace="volunteer")),
    path("admin/", admin.site.urls),
    # Override two allauth views so finishing returns to the account page (the
    # hub) instead of LOGIN_REDIRECT_URL. Must precede the allauth include.
    path(
        "accounts/password/change/",
        portal_account_views.AccountPasswordChangeView.as_view(),
        name="account_change_password",
    ),
    path(
        "accounts/email/",
        portal_account_views.AccountEmailView.as_view(),
        name="account_email",
    ),
    path("accounts/", include("allauth.urls")),
    path("sponsorship/", include("sponsorship.urls", namespace="sponsorship")),
    path("webhooks/", include("webhooks.urls", namespace="webhooks")),
    path(
        "portal_account/",
        include("portal_account.urls", namespace="portal_account"),
    ),
    path(
        "teams/",
        volunteer_view.TeamList.as_view(),
        name="teams",
    ),
    path(
        "teams/mine/",
        volunteer_view.MyTeamsView.as_view(),
        name="my_teams",
    ),
    path(
        "teams/new/",
        volunteer_view.TeamCreate.as_view(),
        name="team_new",
    ),
    path(
        "chapters/",
        volunteer_view.PyladiesChaptersList.as_view(),
        name="chapters",
    ),
    path(
        "teams/<int:pk>",
        volunteer_view.TeamView.as_view(),
        name="team_detail",
    ),
    path(
        "teams/<int:pk>/dashboard/",
        volunteer_view.TeamDashboardView.as_view(),
        name="team_dashboard",
    ),
    path(
        "teams/<int:pk>/edit/",
        volunteer_view.TeamUpdate.as_view(),
        name="team_edit",
    ),
    path(
        "teams/<int:pk>/delete/",
        volunteer_view.TeamDelete.as_view(),
        name="team_delete",
    ),
    path("i18n/", include("django.conf.urls.i18n")),
    path(
        "stats/",
        views.stats,
        name="portal_stats",
    ),
    path(
        "stats.json",
        views.stats_json,
        name="portal_stats_json",
    ),
    path(
        "stats/comparison/",
        views.stats_comparison,
        name="portal_stats_comparison",
    ),
    path(
        "dashboard_gallery",
        views.dashboard_gallery,
        name="dashboard_gallery",
    ),
    path(
        "conference/start-new-year/",
        views.StartNewYearView.as_view(),
        name="start_new_year",
    ),
    path(
        "conferences/",
        views.ConferenceList.as_view(),
        name="conference_list",
    ),
    path(
        "conferences/<int:pk>/edit/",
        views.ConferenceUpdate.as_view(),
        name="conference_edit",
    ),
    path(
        "conferences/<int:pk>/delete/",
        views.ConferenceDelete.as_view(),
        name="conference_delete",
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
