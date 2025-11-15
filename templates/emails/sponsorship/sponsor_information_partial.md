## Sponsorship Information

- **Sponsor Organization Name:** {{ profile.organization_name }}
- **Sponsorship Tier:** {{ profile.sponsorship_tier }}
- **Company Description:** {{ profile.company_description }}
- **Sponsor Progress Status:** {{ profile.get_progress_status_display }}
- **Sponsor Contact Name:** {{ profile.sponsor_contact_name }}
- **Sponsor Contact Email:** {{ profile.sponsors_contact_email }}
- **Sponsor Address:** {{ profile.organization_address }}
- **Sponsorship Amount:** {% if profile.sponsorship_override_amount %}Custom Amount: {{ profile.sponsorship_override_amount }}{% else %}As per tier: {{ profile.sponsorship_tier.amount }}{% endif %}
 - **PO Number:** {% if profile.po_number %}{{ profile.po_number }}{% else %}N/A{% endif %}
- **Internal Contact User:** {{ profile.main_contact_user.get_full_name }}