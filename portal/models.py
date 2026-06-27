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

    def clone_teams_from(self, source):
        """Copy the team structure from another edition into this one.

        Copies each team's name, description, and open-to-new-members flag but
        not its team leads (those are per-edition volunteers). Teams whose name
        already exists in this edition are skipped, so it is safe to run more
        than once. Returns the number of teams created.
        """
        from volunteer.models import Team

        existing = set(self.teams.values_list("short_name", flat=True))
        created = 0
        for team in source.teams.all():
            if team.short_name in existing:
                continue
            Team.objects.create(
                conference=self,
                short_name=team.short_name,
                description=team.description,
                open_to_new_members=team.open_to_new_members,
            )
            created += 1
        return created

    def freeze_stats(self):
        """Snapshot this edition's live metrics into ``historical_snapshot``.

        Once frozen, the comparison and historical-fallback views read these
        fixed numbers instead of recomputing them, so a closed edition's stats
        stay final. Amounts are stored as floats so the dict is JSON-safe.
        Returns the snapshot dict.
        """
        from portal.common import (
            get_attendee_count_cache,
            get_donors_count_cache,
            get_sponsorship_committed_amount_stats_cache,
            get_sponsorship_committed_count_stats_cache,
            get_total_donations_amount_cache,
        )

        self.historical_snapshot = {
            "registrations": get_attendee_count_cache(self),
            "sponsors": get_sponsorship_committed_count_stats_cache(self),
            "sponsorship_amount": float(
                get_sponsorship_committed_amount_stats_cache(self)
            ),
            "donors": get_donors_count_cache(self),
            "donation_amount": float(get_total_donations_amount_cache(self)),
        }
        self.save()
        return self.historical_snapshot

    def clone_sponsorship_tiers_from(self, source):
        """Copy sponsorship tiers (name, amount, description) from another edition.

        Skips tiers whose name already exists in this edition. Returns the
        number of tiers created.
        """
        from sponsorship.models import SponsorshipTier

        existing = set(self.sponsorship_tiers.values_list("name", flat=True))
        created = 0
        for tier in source.sponsorship_tiers.all():
            if tier.name in existing:
                continue
            SponsorshipTier.objects.create(
                conference=self,
                name=tier.name,
                amount=tier.amount,
                description=tier.description,
            )
            created += 1
        return created

    def bring_forward_volunteers_from(self, source):
        """Bring every APPROVED volunteer from another edition into this one.

        Each becomes a PENDING profile (see
        ``VolunteerProfile.bring_forward_to``); volunteers who already have a
        profile here are skipped. Returns the number of profiles created.
        """
        from volunteer.constants import ApplicationStatus

        created = 0
        approved = source.volunteer_profiles.filter(
            application_status=ApplicationStatus.APPROVED
        )
        for profile in approved:
            if profile.bring_forward_to(self) is not None:
                created += 1
        return created
