Dear PSF Accounting Team,

We have an approved sponsorship from **{{ profile.organization_name }}** for PyLadiesCon.

Please prepare the sponsorship contract and invoice with the following information:

## Sponsorship Details

- **Company Name:** {{ profile.organization_name }}
- **Company Address:** {{ profile.organization_address }}
- **Sponsorship Tier:** {{ profile.sponsorship_tier.name }}
- **Sponsorship Amount:** ${{ profile.sponsorship_tier.amount }}{% if profile.sponsorship_override_amount %} (Override Amount: ${{ profile.sponsorship_override_amount }}){% endif %}
- **Contact Name:** {{ profile.sponsor_contact_name }}
- **Contact Email:** {{ profile.sponsors_contact_email }}

Please let us know if you need any additional information.

Best regards,  
PyLadiesCon Team