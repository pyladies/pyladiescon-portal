from django import forms

from .models import SponsorshipProfile


class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        fields = [
            "main_contact_user",
            "additional_contacts",
            "organization_name",
            "sponsorship_type",
            "logo",
            "company_description",
            "amount_to_pay"
        ]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes and attributes
        self.fields['sponsorship_type'].widget.attrs.update({
            'class': 'form-control',
            'id': 'id_sponsorship_type'
        })
        
        self.fields['amount_to_pay'].widget.attrs.update({
            'class': 'form-control',
            'id': 'id_amount_to_pay',
            'step': '0.01',
            'min': '0'
        })
        
        # Add help text to amount field
        self.fields['amount_to_pay'].help_text = (
            "Amount will be auto-filled based on sponsorship type, but can be modified if needed."
        )
        
        # Make amount field not required initially (will be set via JavaScript)
        self.fields['amount_to_pay'].required = False

    def clean_amount_to_pay(self):
        """Ensure amount_to_pay is provided and valid"""
        amount = self.cleaned_data.get('amount_to_pay')
        if amount is None or amount <= 0:
            raise forms.ValidationError("Please enter a valid amount.")
        return amount
        
    def get_sponsorship_prices_json(self):
        """Return sponsorship prices as JSON string for JavaScript"""
        import json
        return json.dumps(SponsorshipProfile.get_sponsorship_prices())