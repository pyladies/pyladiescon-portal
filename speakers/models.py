"""Models for the speaker portal.

Every row is scoped to a ``portal.Conference`` (the design document calls it a
``Project``): that is the portal's per-edition tenant, so PyLadiesCon 2027 is a
new Conference row with the same code. See ``speakers/README.md``.
"""

from django.db import models


class TimestampedModel(models.Model):
    """Abstract base with the portal's ``creation_date``/``modified_date``.

    ``portal.models.BaseModel`` is concrete (multi-table inheritance), so
    every child model gets a reverse accessor on it named after the child
    (``basemodel.session``, ``basemodel.role``...). That forbids any
    BaseModel child from having a field called ``session``, ``presenter``,
    ``role`` or ``language``, all of which this app needs, and costs a join
    on every query. Speakers models therefore share the same two timestamp
    fields through this abstract base instead.
    """

    creation_date = models.DateTimeField(
        "creation_date", editable=False, auto_now_add=True
    )
    modified_date = models.DateTimeField("modified_date", editable=False, auto_now=True)

    class Meta:
        abstract = True


class SpeakerSettings(TimestampedModel):
    """Per-edition configuration for the speaker module.

    One row per Conference, created by an organizer (admin) when the edition
    starts using the speaker portal. Holds the feature flag now and, in later
    stages, the edition's program visibility, pretix and media settings.
    """

    conference = models.OneToOneField(
        "portal.Conference",
        on_delete=models.CASCADE,
        related_name="speaker_settings",
    )
    speaker_module_enabled = models.BooleanField(
        default=False,
        help_text="Turn the speaker portal on for this edition.",
    )

    class Meta:
        verbose_name = "speaker settings"
        verbose_name_plural = "speaker settings"

    def __str__(self):
        return f"Speaker settings ({self.conference})"


def speaker_module_enabled(conference):
    """Whether the speaker module is switched on for ``conference``.

    False when there is no conference, no settings row, or the flag is off, so
    a freshly created edition is off until an organizer opts in.
    """
    if conference is None:
        return False
    return SpeakerSettings.objects.filter(
        conference=conference, speaker_module_enabled=True
    ).exists()
