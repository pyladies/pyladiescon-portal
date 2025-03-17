from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="volunteer_index"),
]
