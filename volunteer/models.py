import re

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.functional import cached_property

from portal.models import BaseModel, ChoiceArrayField
from portal.validators import validate_linked_in_pattern

from .constants import ApplicationStatus, Region, RoleTypes
from .languages import LANGUAGES

APPLICATION_STATUS_CHOICES = [
    (ApplicationStatus.PENDING, ApplicationStatus.PENDING),
    (ApplicationStatus.APPROVED, ApplicationStatus.APPROVED),
    (ApplicationStatus.REJECTED, ApplicationStatus.REJECTED),
    (ApplicationStatus.CANCELLED, ApplicationStatus.CANCELLED),
    (ApplicationStatus.WAITLISTED, ApplicationStatus.WAITLISTED),
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


class Team(BaseModel):
    short_name = models.CharField("name", max_length=40)
    description = models.CharField("description", max_length=1000)
    team_leads = models.ManyToManyField(
        "volunteer.VolunteerProfile",
        verbose_name="team leads",
        related_name="team_leads",
    )
    open_to_new_members = models.BooleanField(default=True)

    def __str__(self):
        return self.short_name

    @cached_property
    def approved_members(self):
        """Return all members with approved volunteer profiles."""
        return self.members.filter(application_status=ApplicationStatus.APPROVED)

    @cached_property
    def pending_members(self):
        """Return all members with pending volunteer profiles."""
        return self.members.filter(application_status=ApplicationStatus.PENDING)

    @cached_property
    def waitlisted_members(self):
        """Return all members with waitlisted volunteer profiles."""
        return self.members.filter(application_status=ApplicationStatus.WAITLISTED)


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
    discord_username = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        verbose_name="Discord username (required)",
        help_text="Required - Your Discord username for team communication",
        default="",
    )
    instagram_username = models.CharField(max_length=50, blank=True, null=True)
    bluesky_username = models.CharField(max_length=100, blank=True, null=True)
    mastodon_url = models.CharField(max_length=100, blank=True, null=True)
    x_username = models.CharField(max_length=100, blank=True, null=True)
    linkedin_url = models.CharField(max_length=100, blank=True, null=True)
    languages_spoken = ChoiceArrayField(
        models.CharField(max_length=32, blank=True, choices=LANGUAGES)
    )
    teams = models.ManyToManyField(
        "volunteer.Team", verbose_name="members", related_name="members", blank=True
    )
    pyladies_chapter = models.CharField(max_length=50, blank=True, null=True)
    additional_comments = models.CharField(max_length=1000, blank=True, null=True)
    availability_hours_per_week = models.PositiveIntegerField(default=1)
    region = models.CharField(
        max_length=50,
        choices=REGION_CHOICES,
        default=Region.NO_REGION,
    )

    @cached_property
    def is_approved(self):
        """Returns True if the volunteer profile is approved."""
        return self.application_status == ApplicationStatus.APPROVED

    @cached_property
    def is_pending(self):
        """Returns False if the volunteer profile is pending."""
        return self.application_status == ApplicationStatus.PENDING

    def clean(self):
        super().clean()
        self._validate_github_username()
        self._validate_discord_username()
        self._validate_instagram_username()
        self._validate_bluesky_username()
        self._validate_mastodon_url()
        self._validate_x_username()
        self._validate_linkedin_url()

    def _validate_github_username(self):
        if self.github_username:
            if not re.match(
                r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$",
                self.github_username,
            ):
                raise ValidationError(
                    {
                        "github_username": "GitHub username can only contain alphanumeric characters and hyphens, "
                        "cannot start or end with a hyphen, and must be between 1-39 characters."
                    }
                )

    def _validate_discord_username(self):
        if self.discord_username:
            if not re.match(
                r"^(?=.{2,32}$)(?!.*\.\.)[a-zA-Z0-9._]+$",
                self.discord_username,
            ):
                if len(self.discord_username) < 2 or len(self.discord_username) > 32:
                    raise ValidationError(
                        {
                            "discord_username": "Discord username must be between 2 and 32 characters."
                        }
                    )
                else:
                    raise ValidationError(
                        {
                            "discord_username": "Discord username must consist of alphanumeric characters, "
                            "periods, underscores, and cannot have two consecutive periods."
                        }
                    )

    def _validate_instagram_username(self):
        if self.instagram_username:
            if not re.match(r"^[a-zA-Z0-9._]{1,30}$", self.instagram_username):
                raise ValidationError(
                    {
                        "instagram_username": "Instagram username can only contain alphanumeric characters, "
                        "periods, and underscores, and must be between 1-30 characters."
                    }
                )

    def _validate_bluesky_username(self):
        if self.bluesky_username:
            if not re.match(
                r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,28}[a-zA-Z0-9](\.[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})?$",
                self.bluesky_username,
            ):
                raise ValidationError(
                    {
                        "bluesky_username": "Invalid Bluesky username format. "
                        "Should be either a simple username or a full handle (e.g., username.bsky.social)."
                    }
                )

    def _validate_mastodon_url(self):
        if self.mastodon_url:
            mastodon_pattern1 = r"^@[a-zA-Z0-9_]+@[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"  # @user@instance.tld
            mastodon_pattern2 = r"^https?://[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/@[a-zA-Z0-9_]+$"  # https://instance.tld/@user

            if not (
                re.match(mastodon_pattern1, self.mastodon_url)
                or re.match(mastodon_pattern2, self.mastodon_url)
            ):
                raise ValidationError(
                    {
                        "mastodon_url": "Invalid Mastodon URL format. "
                        "Should be either @username@instance.tld or https://instance.tld/@username."
                    }
                )

    def _validate_x_username(self):
        if self.x_username:
            if not re.match(r"^[a-zA-Z0-9_]{1,15}$", self.x_username):
                raise ValidationError(
                    {
                        "x_username": "X/Twitter username can only contain alphanumeric characters and underscores, "
                        "and must be between 1-15 characters."
                    }
                )

    def _validate_linkedin_url(self):
        if self.linkedin_url:
            if not validate_linked_in_pattern(self.linkedin_url):
                raise ValidationError(
                    {
                        "linkedin_url": "Invalid LinkedIn URL format. "
                        "Example: linkedin.com/in/username or https://www.linkedin.com/in/username."
                    }
                )

    def __str__(self):
        return self.user.username

    def get_absolute_url(self):
        return reverse("volunteer:volunteer_profile_edit", kwargs={"pk": self.pk})


def _send_email(
    subject, recipient_list, *, html_template=None, text_template=None, context=None
):
    """Helper function to send an email."""
    context = context or {}
    context["current_site"] = Site.objects.get_current()
    text_content = render_to_string(
        text_template,
        context=context,
    )
    html_content = render_to_string(
        html_template,
        context=context,
    )
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_volunteer_notification_email(instance, updated=False):
    """Send email to the user whenever their volunteer profile was updated/created."""
    context = {"profile": instance}
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application"
    if updated:
        context["updated"] = True
        subject += " Updated"
    else:
        subject += " Received"
    if instance.application_status == ApplicationStatus.WAITLISTED:
        html_template = "volunteer/email/team_is_now_closed.html"
        text_template = "volunteer/email/team_is_now_closed.txt"
    else:
        html_template = "volunteer/email/volunteer_profile_email_notification.html"
        text_template = "volunteer/email/volunteer_profile_email_notification.txt"

    _send_email(
        subject,
        [instance.user.email],
        html_template=html_template,
        text_template=text_template,
        context=context,
    )


def send_volunteer_onboarding_email(instance):
    """Send the volunteer onboarding email when their volunteer profile has been updated.
    This should only be sent when the volunteer profile is approved.
    """
    if instance.application_status == ApplicationStatus.APPROVED:
        context = {"profile": instance, "GDRIVE_FOLDER_ID": settings.GDRIVE_FOLDER_ID}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Welcome to the PyLadiesCon Volunteer Team"

        for role in instance.roles.all():
            if role.short_name in [RoleTypes.ADMIN, RoleTypes.STAFF]:
                context["admin_onboarding"] = True
        html_template = "volunteer/email/new_volunteer_onboarding.html"
        text_template = "volunteer/email/new_volunteer_onboarding.txt"
        _send_email(
            subject,
            [instance.user.email],
            html_template=html_template,
            text_template=text_template,
            context=context,
        )


def send_internal_volunteer_onboarding_email(instance):
    """Notify internal team about a new volunteer onboarding.
    This should only be sent when the volunteer profile is approved.

    Send notification email to staff and admin team members
    """
    if instance.application_status == ApplicationStatus.APPROVED:
        context = {"profile": instance, "GDRIVE_FOLDER_ID": settings.GDRIVE_FOLDER_ID}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Complete the Volunteer Onboarding for: {instance.user.first_name} {instance.user.last_name}"
        for role in instance.roles.all():
            if role.short_name in [RoleTypes.ADMIN, RoleTypes.STAFF]:
                context["admin_onboarding"] = True
        html_template = "volunteer/email/internal_volunteer_onboarding.html"
        text_template = "volunteer/email/internal_volunteer_onboarding.txt"
        _send_internal_email(
            subject,
            html_template=html_template,
            text_template=text_template,
            context=context,
        )


def _send_internal_email(
    subject, *, html_template=None, text_template=None, context=None
):
    """Helper function to send an internal email.

    Lookup who the internal team members who should receive the email and then send the emails individually.
    """

    recipients = User.objects.filter(
        Q(
            id__in=VolunteerProfile.objects.prefetch_related("roles")
            .filter(roles__short_name__in=[RoleTypes.ADMIN, RoleTypes.STAFF])
            .values_list("id", flat=True)
        )
        | Q(is_superuser=True)
        | Q(is_staff=True)
    ).distinct()
    # TODO Roles need to use django model choices not enum

    if not recipients.exists():
        return

    # send each email individually to each recipient, for privacy reasons
    for recipient in recipients:
        context["recipient_name"] = recipient.get_full_name() or recipient.username

        _send_email(
            subject,
            [recipient.email],
            html_template=html_template,
            text_template=text_template,
            context=context,
        )


def send_internal_notification_email(instance):
    """Send email to the team whenever a new volunteer profile is created.

    Emails will be sent to team members with the role type Staff or Admin.
    Emails will also be sent to users with is_superuser or is_staff set to True.

    """
    context = {"profile": instance}
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Volunteer Application"

    text_template = "volunteer/email/internal_volunteer_profile_email_notification.txt"

    html_template = "volunteer/email/internal_volunteer_profile_email_notification.html"

    _send_internal_email(
        subject,
        html_template=html_template,
        text_template=text_template,
        context=context,
    )


@receiver(post_save, sender=VolunteerProfile)
def volunteer_profile_signal(sender, instance, created, **kwargs):
    """Things to do whenever a volunteer profile is created or updated.

    Send a notification email to the user to confirm their volunteer application status.
    """
    if created:
        send_internal_notification_email(instance)
        send_volunteer_notification_email(instance)
    else:
        # no need to send email to internal team for VolunteerProfile updates (e.g. changing username, etc)
        send_volunteer_notification_email(instance, updated=True)
