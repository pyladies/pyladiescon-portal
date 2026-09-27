"""The record of every email the portal sent a person (task 2.23).

One row per send, written by ``common.send_emails.send_email``, which every
app's mail already passes through. Account emails (sign-in codes, password
resets, address verification) go through the allauth adapter instead and
are deliberately not recorded: they carry secrets.
"""

from datetime import timedelta

import bleach
from django.conf import settings
from django.db import models
from django.utils import timezone

from .markdown_emails import MarkdownEmailRenderer

# The email's own allowlist with image sources dropped (``SentEmail.body_html``).
TRAIL_ATTRIBUTES = {**MarkdownEmailRenderer.ALLOWED_ATTRIBUTES, "img": ["alt"]}


class SentEmailStatus(models.TextChoices):
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class SentEmailQuerySet(models.QuerySet):
    def owned_by(self, user):
        """The records that are ``user``'s to read.

        Theirs when the record's account is theirs, or the presenter it was
        sent to is linked to their account, which is what lets a speaker see
        the invitation that arrived before their account existed. Never by
        address alone: an organizer can type an address into a presenter
        row before anyone has proven it is theirs.
        """
        return self.filter(models.Q(user=user) | models.Q(presenter__user=user))

    def past_retention(self, today=None):
        """Records kept longer than the edition plus the retention period.

        An edition ends on its ``end_date``, or on the last day of its year
        when none is set. A record with no edition (a sponsorship notice,
        say) is measured from when it was sent.
        """
        today = today or timezone.localdate()
        cutoff = today - timedelta(days=settings.EMAIL_RECORD_RETENTION_DAYS)
        return self.filter(
            models.Q(conference__isnull=True, sent_at__date__lt=cutoff)
            | models.Q(conference__end_date__lt=cutoff)
            | models.Q(
                conference__end_date__isnull=True, conference__year__lt=cutoff.year
            )
        )


class SentEmail(models.Model):
    """One email the portal sent: to whom, what, and whether it went."""

    conference = models.ForeignKey(
        "portal.Conference",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_emails",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emails_received",
        help_text="The account it was sent to, when the sender knew it.",
    )
    presenter = models.ForeignKey(
        "speakers.Presenter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_emails",
        help_text="The presenter it was sent to, when it went to one.",
    )
    session = models.ForeignKey(
        "speakers.Session",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_emails",
    )
    to = models.TextField("to", help_text="The addresses as sent.")
    subject = models.CharField(max_length=500)
    template = models.CharField(
        max_length=200, help_text="The Markdown template: what kind of email."
    )
    body_md = models.TextField(
        blank=True, help_text="The rendered Markdown, the source of both parts."
    )
    context_digest = models.JSONField(
        default=dict, blank=True, help_text="Ids of what it was about."
    )
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=8, choices=SentEmailStatus.choices, default=SentEmailStatus.SENT
    )
    error = models.TextField(blank=True)

    objects = SentEmailQuerySet.as_manager()

    class Meta:
        ordering = ["-sent_at", "-id"]
        verbose_name = "sent email"
        verbose_name_plural = "sent emails"

    def __str__(self):
        return f"{self.subject} -> {self.to}"

    @property
    def kind(self):
        """``speakers/invitation`` for ``emails/speakers/invitation.md``."""
        return kind_of(self.template)

    @property
    def failed(self):
        return self.status == SentEmailStatus.FAILED

    @property
    def body_html(self):
        """The body as the HTML part was, through the same renderer and the
        same bleach whitelist, minus image sources: a presenter's title or
        name can carry an image, and the trail is where a maintainer reads
        other people's mail in bulk, so nothing here fetches from a third
        party and reports who looked, and when."""
        html = MarkdownEmailRenderer().markdown_to_html(self.body_md)
        return bleach.clean(
            html,
            tags=MarkdownEmailRenderer.ALLOWED_TAGS,
            attributes=TRAIL_ATTRIBUTES,
            strip=True,
        )


def kind_of(template):
    """The template path with the ``emails/`` prefix and ``.md`` suffix off."""
    name = template.removeprefix("emails/")
    return name.removesuffix(".md")


def prune_sent_emails(dry_run=False):
    """Delete the records past retention; return how many."""
    expired = SentEmail.objects.past_retention()
    if dry_run:
        return expired.count()
    count, _ = expired.delete()
    return count
