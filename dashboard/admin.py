from django.contrib import admin
from .models import SponsorshipApplication, VolunteerTask, StaffTask

# Register your models here.
admin.site.register(SponsorshipApplication)
admin.site.register(VolunteerTask)
admin.site.register(StaffTask)

