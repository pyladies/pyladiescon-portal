from django.urls import path
from .views import staffteam_dashboard, sponsorship_dashboard, volunteer_dashboard


app_name = "dashboard"

urlpatterns = [
    path("dashboard/", staffteam_dashboard, name="team_dashboard"),
    path("dashboard/sponsorship/", sponsorship_dashboard, name="sponsorship_dashboard"),
    path("dashboard/volunteer/", volunteer_dashboard, name="volunteer_dashboard"),
]