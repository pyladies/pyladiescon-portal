from django import forms
from django.db import models
from django.utils.timezone import now
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.postgres.fields import ArrayField


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {
            "form_class": forms.TypedMultipleChoiceField,
            "choices": self.base_field.choices,
            "coerce": self.base_field.to_python,
            "widget": FilteredSelectMultiple(self.verbose_name, False),
        }
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)


class BaseModel(models.Model):
    creation_date = models.DateTimeField("creation_date", default=now, editable=False)
    modified_date = models.DateTimeField("modified_date", default=now, editable=False)

    def save(self, *args, **kwargs):
        self.modified_date = now()
        if "update_fields" in kwargs and "modified_date" not in kwargs["update_fields"]:
            kwargs["update_fields"].append("modified_date")
        super().save(*args, **kwargs)
