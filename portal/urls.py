"""
URL configuration for the portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views:
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views:
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf:
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path

from portal import views

urlpatterns = [
    path("", views.index, name="index"),  # URL for the homepage
    path("volunteer/", include("volunteer.urls", namespace="volunteer")),  # Included volunteer app URLs with a namespace
    path("admin/", admin.site.urls),  # URL for Django's admin panel
    path("accounts/", include("allauth.urls")),  # Included Django AllAuth authentication URLs
    path("portal_account/", include("portal_account.urls", namespace="portal_account")),  # Included portal_account app URLs with a namespace
]

# Changes made:
# 1. Added a namespace for "portal_account" URLs.
# 2. Added a namespace for "volunteer" URLs.
# 3. The overall structure remains the same, but the addition of namespaces is a major change.
