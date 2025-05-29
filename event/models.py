from django.db import models

from portal.models import BaseModel

class Event(BaseModel):
    event_slug = models.CharField(blank=True, null=False)

