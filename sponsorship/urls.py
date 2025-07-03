from django.urls import path
from . import views

app_name = 'sponsorship'

urlpatterns = [
    path('create/', views.create_sponsorship_profile, name='create_sponsorship_profile'),
]
