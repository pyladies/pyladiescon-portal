# Individual Donations Tracking

## Overview

The sponsorship system now supports separating individual donations from corporate sponsorships. This allows for better tracking and visualization of different funding sources.

## Features

### Model Changes

A new boolean field `is_individual_donation` has been added to the `SponsorshipProfile` model:

```python
is_individual_donation = models.BooleanField(
    default=False,
    help_text="Check if this is an individual donation (not a corporate sponsorship)",
)
```

### New Stats Available

The following new statistics are now calculated and cached:

- **Individual Donations Count**: Number of paid individual donations
- **Individual Donations Amount**: Total amount raised from individual donations
- **Corporate Sponsors Count**: Number of paid corporate sponsors (excludes individual donations)
- **Corporate Sponsors Amount**: Total amount raised from corporate sponsors (excludes individual donations)
- **Total Funds Raised**: Sum of corporate sponsors and individual donations

### Cache Keys

New cache keys in `portal/constants.py`:

```python
CACHE_KEY_INDIVIDUAL_DONATIONS_COUNT = "individual_donations_count"
CACHE_KEY_INDIVIDUAL_DONATIONS_AMOUNT = "individual_donations_amount"
CACHE_KEY_CORPORATE_SPONSORS_COUNT = "corporate_sponsors_count"
CACHE_KEY_CORPORATE_SPONSORS_AMOUNT = "corporate_sponsors_amount"
CACHE_KEY_TOTAL_FUNDS_RAISED = "total_funds_raised"
```

## Usage

### Admin Interface

1. Navigate to the Django admin panel
2. Go to Sponsorship Profiles
3. When creating or editing a profile, check the "Is individual donation" checkbox for individual donations
4. The field is also available as a filter in the admin list view

### Viewing Stats

The public stats page (`/stats/`) now displays a "Fundraising Breakdown" section showing:

- Individual Donations (count and amount)
- Corporate Sponsors (count and amount)
- Total Funds Raised
- Progress to Goal

The original "Sponsorship Pipeline" section remains available for detailed tracking.

### API/Code Usage

To access these stats in your code:

```python
from portal.common import (
    get_individual_donations_count_cache,
    get_individual_donations_amount_cache,
    get_corporate_sponsors_count_cache,
    get_corporate_sponsors_amount_cache,
    get_total_funds_raised_cache,
)

# Get individual donations stats
individual_count = get_individual_donations_count_cache()
individual_amount = get_individual_donations_amount_cache()

# Get corporate sponsors stats
corporate_count = get_corporate_sponsors_count_cache()
corporate_amount = get_corporate_sponsors_amount_cache()

# Get total funds raised
total_funds = get_total_funds_raised_cache()
```

## Implementation Details

### Calculation Logic

- **Paid Status Only**: All calculations only count sponsorship profiles with `progress_status=PAID`
- **Override Handling**: Properly handles both `sponsorship_tier.amount` and `sponsorship_override_amount`
- **Separation**: Uses `is_individual_donation` to filter between individual and corporate

### Template Integration

The stats are automatically available in the `stats` context variable in templates that use `get_sponsorships_stats_dict()`.

Example template usage:

```django
{{ stats.individual_donations_count }}
{{ stats.individual_donations_amount|as_currency }}
{{ stats.corporate_sponsors_count }}
{{ stats.corporate_sponsors_amount|as_currency }}
{{ stats.total_funds_raised|as_currency }}
```

## Testing

Tests are available in `tests/portal/test_common.py`:

```bash
# Run specific test
docker compose run --rm web pytest tests/portal/test_common.py::TestGetStatsCachedValues::test_individual_donations_stats -v

# Run all common tests
docker compose run --rm web pytest tests/portal/test_common.py -v
```

## Migration

The migration `sponsorship/migrations/0005_sponsorshipprofile_is_individual_donation.py` adds the new field with a default value of `False`, so existing sponsorship profiles are automatically treated as corporate sponsorships (not individual donations).

To mark existing profiles as individual donations, update them via:

1. Django admin interface
2. Django shell:
   ```python
   from sponsorship.models import SponsorshipProfile
   
   # Mark a specific profile as individual donation
   profile = SponsorshipProfile.objects.get(organization_name="John Doe")
   profile.is_individual_donation = True
   profile.save()
   ```

## Cache Management

All stats use Django's cache system with a 5-minute timeout (`STATS_CACHE_TIMEOUT`). To clear the cache:

```python
from django.core.cache import cache
from portal.constants import (
    CACHE_KEY_INDIVIDUAL_DONATIONS_COUNT,
    CACHE_KEY_INDIVIDUAL_DONATIONS_AMOUNT,
    CACHE_KEY_CORPORATE_SPONSORS_COUNT,
    CACHE_KEY_CORPORATE_SPONSORS_AMOUNT,
    CACHE_KEY_TOTAL_FUNDS_RAISED,
)

cache.delete(CACHE_KEY_INDIVIDUAL_DONATIONS_COUNT)
cache.delete(CACHE_KEY_INDIVIDUAL_DONATIONS_AMOUNT)
cache.delete(CACHE_KEY_CORPORATE_SPONSORS_COUNT)
cache.delete(CACHE_KEY_CORPORATE_SPONSORS_AMOUNT)
cache.delete(CACHE_KEY_TOTAL_FUNDS_RAISED)
```

## Related Issues

- Fixes #247 - Separate the "Individual Donations" stats
