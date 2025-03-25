from django.forms import ModelForm
from .models import VolunteerProfile


class VolunteerProfileForm(ModelForm):

    class Meta:
        model = VolunteerProfile
        exclude = ["user", "application_status"]

    def clean(self):
        cleaned_data = super().clean()
        print("cleaned data volunteer form")
        print(cleaned_data)
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        """ """
        user = self.user
        self.instance.user = user
        print("languegs")
        print(self.cleaned_data["languages_spoken"])
        volunteer_profile = super().save(commit)
        return volunteer_profile
