from django.forms import ModelForm

from .models import VolunteerProfile


class VolunteerProfileForm(ModelForm):

    class Meta:
        model = VolunteerProfile
        exclude = ["user", "application_status"]

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            pass

    def save(self, commit=True):
        """ """
        user = self.user
        self.instance.user = user
        volunteer_profile = super().save(commit)
        return volunteer_profile
