from django.contrib import admin
from .models import VolunteerProfile, Role, Team

admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile)
