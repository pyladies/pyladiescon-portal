<<<<<<< HEAD
from . import views
from django.urls import path, include


app_name = 'sponsorship'

urlpatterns = [
    path('profile/new/', views.create_sponsorship_profile, name='create'),
    path('profile/success/', views.sponsorship_success, name='success'),

=======
from django.urls import path

from . import views

app_name = "sponsorship"

urlpatterns = [
    path(
        "create/", views.create_sponsorship_profile, name="create_sponsorship_profile"
    ),
>>>>>>> pyladies/main
]
