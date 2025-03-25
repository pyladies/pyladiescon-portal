from django.db import models
from portal.models import BaseModel

# Create your models here.
from django.urls import reverse
from django.contrib.auth.models import User


class PortalProfile(BaseModel):

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    pronouns = models.CharField(max_length=100, blank=True, null=True)
    coc_agreement = models.BooleanField(default=False)

    def get_absolute_url(self):
        return reverse("portal_account:portal_profile_edit", kwargs={"pk": self.pk})

    def __str__(self):
        return self.user.username
