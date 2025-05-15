from django import forms
from django.forms import ModelForm

from .models import PortalProfile


class PortalProfileForm(ModelForm):

    username = forms.CharField(disabled=True)
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(disabled=True)
    coc_agreement = forms.BooleanField(required=False)
    tos_agreement = forms.BooleanField(required=False)

    class Meta:
        model = PortalProfile
        fields = ["pronouns", "profile_picture", "coc_agreement", "tos_agreement"]

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

        if self.instance.pk:
            if self.instance.coc_agreement and self.instance.tos_agreement:
                self.fields["coc_agreement"].disabled = True
                self.fields["tos_agreement"].disabled = True

        # fix field order
        self.order_fields(
            [
                "username",
                "first_name",
                "last_name",
                "email",
                "pronouns",
                "profile_picture",
                "coc_agreement",
                "tos_agreement",
            ]
        )

    def save(self, commit=True):
        """ """
        user = self.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        self.instance.user = user
        portal_profile = super().save(commit)
        return portal_profile
