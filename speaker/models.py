import re

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse

from portal.models import BaseModel

from .constants import ApplicationStatus, Region
from .languages import LANGUAGES

APPLICATION_STATUS_CHOICES = [
    (ApplicationStatus.PENDING, ApplicationStatus.PENDING),
    (ApplicationStatus.APPROVED, ApplicationStatus.APPROVED),
    (ApplicationStatus.REJECTED, ApplicationStatus.REJECTED),
    (ApplicationStatus.CANCELLED, ApplicationStatus.CANCELLED),
]

REGION_CHOICES = [
    (Region.NO_REGION, Region.NO_REGION),
    (Region.NORTH_AMERICA, Region.NORTH_AMERICA),
    (Region.SOUTH_AMERICA, Region.SOUTH_AMERICA),
    (Region.EUROPE, Region.EUROPE),
    (Region.AFRICA, Region.AFRICA),
    (Region.ASIA, Region.ASIA),
    (Region.OCEANIA, Region.OCEANIA),
]


# # Pretalx Data
#   {
#      "code": "WPSKUD",
#      "name": "Maya Kerostasia",
#      "biography": "blah blah blah",
#      "submissions": [
#        "DBZ7HS"
#      ],
#      "avatar_url": "",
#      "answers": [],
#      "email": "mayakerostasia@gmail.com",
#      "timezone": "UTC",
#      "locale": "en",
#      "has_arrived": false
#   }


class SpeakerProfile(BaseModel):
    # Identification
    # id = models.AutoField()
    application_status = models.CharField(
        max_length=50,
        choices=APPLICATION_STATUS_CHOICES,
        default=ApplicationStatus.PENDING,
    )

    # Pretalx Data
    code = models.CharField(blank=True, null=False, unique=True)
    name = models.CharField(blank=True, null=True)
    biography = models.CharField(blank=True, null=True)
    avatar_url = models.CharField(blank=True, null=True)
    email = models.CharField(blank=True, null=True) 
    timezone = models.CharField(blank=True, null=True)
    locale = models.CharField(blank=True, null=True)
    has_arrived = models.BooleanField(blank=True, null=True)
    submissions = models.JSONField(blank=True, null=True)
    answers =  models.JSONField(blank=True, null=True)

    additional_comments = models.CharField(max_length=1000, blank=True, null=True)

    # region = models.CharField(
    #     max_length=50,
    #     choices=REGION_CHOICES,
    #     default=Region.NO_REGION,
    # )

    def clean(self):
        super().clean()

    def __str__(self):
        return str(self.name)

    def get_absolute_url(self):
        return reverse("speaker:speaker_profile_edit", kwargs={"pk": self.pk})

def send_speaker_notification_email(instance, updated=False):
    """Send email to the user whenever their speaker profile was updated/created."""
    context = {"profile": instance, "current_site": Site.objects.get_current()}
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Speaker Application"
    if updated:
        context["updated"] = True
        subject += " Updated"
    else:
        subject += " Received"
    text_content = render_to_string(
        "speaker/email/speaker_profile_email_notification.txt",
        context=context,
    )
    html_content = render_to_string(
        "speaker/email/speaker_profile_email_notification.html",
        context=context,
    )

    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [instance.email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


@receiver(post_save, sender=SpeakerProfile)
def speaker_profile_signal(sender, instance, created, **kwargs):
    """Things to do whenever a speaker profile is created or updated.

    Send a notification email to the user to confirm their speaker application status.
    """
    if created:
        send_speaker_notification_email(instance)
    else:
        send_speaker_notification_email(instance, updated=True)


