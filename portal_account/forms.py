from django import forms
from django.forms import ModelForm

from .models import PortalProfile


class PortalProfileForm(ModelForm):

    username = forms.CharField(disabled=True)
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(disabled=True)

    class Meta:
        model = PortalProfile
        fields = ["pronouns", "coc_agreement"]

    def clean(self):
        cleaned_data = super().clean()
        self.instance.username = cleaned_data.get("username")
        self.email = cleaned_data.get("email")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["username"].initial = self.user.username
            self.fields["email"].initial = self.user.email
            self.fields["first_name"].initial = self.user.first_name
            self.fields["last_name"].initial = self.user.last_name

    def save(self, commit=True):
        """ """
        user = self.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        self.instance.user = user
        portal_profile = super().save(commit)
        return portal_profile
