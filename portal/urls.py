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
from volunteer import views as volunteer_view

urlpatterns = [
    path("", views.index, name="index"),
    path("volunteer/", include("volunteer.urls", namespace="volunteer")),
    path("speaker/", include("speaker.urls", namespace="speaker")),
    path("event/", include("event.urls", namespace="event")),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
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
        "teams/<int:pk>",
        volunteer_view.TeamView.as_view(),
        name="team_detail",
    ),
    path("i18n/", include("django.conf.urls.i18n")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
