from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.timezone import now


class ChoiceArrayField(ArrayField):

    def formfield(self, **kwargs):  # pragma: no cover
        # Currently this is only used the languages_spoken field but the field is being deprecated
        defaults = {
            "form_class": forms.TypedMultipleChoiceField,
            "choices": self.base_field.choices,
            "coerce": self.base_field.to_python,
            "widget": FilteredSelectMultiple(self.verbose_name, False),
        }
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)


class BaseModel(models.Model):
    creation_date = models.DateTimeField(
        "creation_date", editable=False, auto_now_add=True
    )
    modified_date = models.DateTimeField("modified_date", editable=False, auto_now=True)

    def save(self, *args, **kwargs):
        self.modified_date = now()
        if (
            "update_fields" in kwargs and "modified_date" not in kwargs["update_fields"]
        ):  # pragma: no cover
            kwargs["update_fields"].append("modified_date")
        super().save(*args, **kwargs)


class Conference(BaseModel):
    """A single PyLadiesCon edition (2023, 2024, 2025, ...).

    Anchors all per-year configuration. Exactly one conference is active at a
    time; see ``save()`` and ``get_active()``. See
    ``docs/architecture/multi-year-conferences.md`` for the full design.
    """

    # BaseModel is concrete (multi-table inheritance), so without this
    # explicit parent link Django adds a reverse accessor named "conference"
    # to BaseModel — clashing with the per-year ``conference`` FK that other
    # models gain. related_name="+" suppresses that accessor.
    basemodel_ptr = models.OneToOneField(
        BaseModel,
        on_delete=models.CASCADE,
        parent_link=True,
        primary_key=True,
        related_name="+",
    )

    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=False)
    pretix_event_slug = models.CharField(max_length=100, blank=True)

    # year-bound config (replaces hardcoded constants)
    sponsorship_goal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    donation_goal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    proposals_count = models.PositiveIntegerField(default=0)

    # year-bound state flags
    volunteer_application_open = models.BooleanField(default=False)
    sponsorship_open = models.BooleanField(default=False)
    accepting_donations = models.BooleanField(default=True)

    # optional metadata
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # When this edition takes place. Next year's conference can only be started
    # once this date has passed. Null for a freshly-created edition.
    conference_date = models.DateField(null=True, blank=True)
    banner_text = models.CharField(max_length=255, blank=True)

    # snapshot of closed-out year metrics (used when no portal data exists,
    # e.g. for 2023 and 2024, and for "freezing" past years)
    historical_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_active:
            Conference.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active conference, or ``None`` if none is set."""
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def can_start_next_year(cls):
        """Whether the "start a new year" flow should be available.

        Available once the active edition's ``conference_date`` has passed, so
        organizers set up next year only after the current edition is over.
        Hidden while the active edition's date is unset or still upcoming. When
        there is no active edition at all, it is available so the first edition
        can be created.
        """
        active = cls.get_active()
        if active is None:
            return True
        if active.conference_date is None:
            return False
        return active.conference_date < now().date()
