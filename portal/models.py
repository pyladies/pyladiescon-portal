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


class FundraisingGoal(BaseModel):
    """Model to store fundraising goals for donations and sponsorships."""

    GOAL_TYPE_CHOICES = [
        ("donation", "Donation Goal"),
        ("sponsorship", "Sponsorship Goal"),
    ]

    goal_type = models.CharField(
        max_length=20,
        choices=GOAL_TYPE_CHOICES,
        unique=True,
        help_text="Type of fundraising goal",
    )
    target_amount = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Target amount for this goal"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this goal is currently active"
    )
    description = models.TextField(
        blank=True, null=True, help_text="Optional description for this goal"
    )

    class Meta:
        verbose_name = "Fundraising Goal"
        verbose_name_plural = "Fundraising Goals"
        ordering = ["goal_type"]

    def __str__(self):
        return f"{self.get_goal_type_display()}: ${self.target_amount}"
