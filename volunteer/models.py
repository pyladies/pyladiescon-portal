from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import models, transaction
from django.conf.global_settings import LANGUAGES
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import BaseModel, ChoiceArrayField
from portal.settings import ACCOUNT_EMAIL_SUBJECT_PREFIX, DEFAULT_FROM_EMAIL
from .constants import ApplicationStatus

TIMEZONE_CHOICES = [
    ("UTC+14", "UTC+14"),
    ("UTC+13", "UTC+13"),
    ("UTC+12", "UTC+12"),
    ("UTC+11", "UTC+11"),
    ("UTC+10", "UTC+10"),
    ("UTC+9", "UTC+9"),
    ("UTC+8", "UTC+8"),
    ("UTC+7", "UTC+7"),
    ("UTC+6", "UTC+6"),
    ("UTC+5", "UTC+5"),
    ("UTC+4", "UTC+4"),
    ("UTC+3", "UTC+3"),
    ("UTC+2", "UTC+2"),
    ("UTC+1", "UTC+1"),
    ("UTC", "UTC"),
    ("UTC-1", "UTC-1"),
    ("UTC-2", "UTC-2"),
    ("UTC-3", "UTC-3"),
    ("UTC-4", "UTC-4"),
    ("UTC-5", "UTC-5"),
    ("UTC-6", "UTC-6"),
    ("UTC-7", "UTC-7"),
    ("UTC-8", "UTC-8"),
    ("UTC-9", "UTC-9"),
    ("UTC-10", "UTC-10"),
    ("UTC-11", "UTC-11"),
    ("UTC-12", "UTC-12"),
]


APPLICATION_STATUS_CHOICES = [
    (ApplicationStatus.PENDING, ApplicationStatus.PENDING),
    (ApplicationStatus.APPROVED, ApplicationStatus.APPROVED),
    (ApplicationStatus.REJECTED, ApplicationStatus.REJECTED),
    (ApplicationStatus.CANCELLED, ApplicationStatus.CANCELLED),
]


class Team(BaseModel):
    short_name = models.CharField("name", max_length=40)
    description = models.CharField("description", max_length=1000)
    team_leads = models.ManyToManyField(
        "volunteer.VolunteerProfile",
        verbose_name="team leads",
        related_name="team_leads",
    )

    def __str__(self):
        return self.short_name


class Role(BaseModel):
    short_name = models.CharField("name", max_length=40)
    description = models.CharField("description", max_length=1000)

    def __str__(self):
        return self.short_name


class VolunteerProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roles = models.ManyToManyField(
        "Role", verbose_name="Roles", related_name="roles", blank=True
    )
    application_status = models.CharField(
        max_length=50,
        choices=APPLICATION_STATUS_CHOICES,
        default=ApplicationStatus.PENDING,
    )

    # social media urls
    github_username = models.CharField(max_length=50, blank=True, null=True)
    discord_username = models.CharField(max_length=50, blank=True, null=True)
    instagram_username = models.CharField(max_length=50, blank=True, null=True)
    bluesky_username = models.CharField(max_length=100, blank=True, null=True)
    mastodon_url = models.CharField(max_length=100, blank=True, null=True)
    x_username = models.CharField(max_length=100, blank=True, null=True)
    linkedin_url = models.CharField(max_length=100, blank=True, null=True)
    languages_spoken = ChoiceArrayField(
        models.CharField(max_length=32, blank=True, choices=LANGUAGES)
    )
    teams = models.ManyToManyField(
        "volunteer.Team", verbose_name="team", related_name="team", blank=True
    )
    pyladies_chapter = models.CharField(max_length=50, blank=True, null=True)

    timezone = models.CharField(max_length=6, choices=TIMEZONE_CHOICES)

    def __str__(self):
        return self.user.username

    def get_absolute_url(self):
        return reverse("volunteer:volunteer_profile_edit", kwargs={"pk": self.pk})

    def save(self):
        def send_volunteer_email():
            text_content = render_to_string("volunteer/email/email_application_status_message.txt",
                                            context={"status": self.application_status,
                                                     "team_names": self.teams,
                                                     "edit_url": self.get_absolute_url(),
                                                     "site_name": "PyLadiesCon"},
                                            )
            html_content = render_to_string("volunteer/email_application_status.html",
                                            context={"status": self.application_status,
                                                     "team_names": self.teams,
                                                     "edit_url": self.get_absolute_url(),
                                                     "site_name": "PyLadiesCon"},
                                            )

            msg = EmailMultiAlternatives(
                f"{ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Status",
                text_content,
                DEFAULT_FROM_EMAIL,
                [self.user.email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()

        transaction.on_commit(send_volunteer_email)
        return super().save()


