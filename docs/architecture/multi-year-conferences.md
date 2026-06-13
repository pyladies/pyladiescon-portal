# Multi-Year Conferences (Architecture)

This document describes how the portal models multiple PyLadiesCon editions
(2023, 2024, 2025, 2026, ...) and why the data is shaped that way. It is the
reference for any work that touches volunteer profiles, sponsorship profiles,
teams, stats, or anything else that should reset year-over-year.

The portal was originally written for PyLadiesCon 2025 with no notion of
conference year. This document captures the design that introduced
year-awareness to the data model.

**Status:** Design locked in. See `multi-year-progress.md` for implementation
progress.

**Last updated:** 2026-05-11

---

## Goals

- Track volunteers and sponsorships per conference year.
- Carry user identity (username, password, email, pronouns, profile picture,
  CoC/ToS agreement) across years without re-creating accounts.
- Allow stats to be viewed per year and compared across years.
- Backfill existing 2025 data under a 2025 Conference row.
- Preserve historical references to PyLadiesCon 2023 and 2024, even though
  those predate the portal.

## Non-goals

- Running multiple active conferences simultaneously. Exactly one
  `Conference.is_active=True` at any time.
- Versioning the CoC or ToS text per year. Agreements remain global flags on
  `PortalProfile`; if the text changes substantively, clear the flag via a
  one-off data migration.
- Replacing Pretix as the source of truth for attendees and ticket orders.
  `PretixOrder` and `AttendeeProfile` continue to flow from Pretix; the
  conference linkage is derived from `event_slug`.

---

## Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Entity name | `Conference` (not `Event`) | Matches product identity. "Event" is already used by Pretix and would collide. |
| App location | `portal/` | Conference is foundational; `portal/` already holds `BaseModel` and shared infrastructure. |
| Active-conference selection | `is_active` boolean on `Conference`, save-time enforcer for single `True` | Smallest schema, no extra singleton needed. Year-bound config also lives on `Conference`, so a separate `SiteConfig` would be redundant. |
| One conference per year | `year` is `unique=True`; multiple conferences in the same year are **not** allowed | `year` is the user-facing identity of a conference: the stats switcher keys on `?year=`, cache keys are namespaced by year (`volunteer_signups_count_2025`), and previous-event choices come from `filter(year__lt=...)`. Two rows sharing a year would make all three ambiguous (e.g. cache-key collisions). PyLadiesCon is one event per year, so the constraint matches reality. If a genuine "two events in one year" need ever arises, model it with distinct slugs rather than relaxing this — `slug` is already unique and serves as the canonical identifier, so new code should prefer it where a stable key is needed. |
| Year-bound config | `donation_goal`, `sponsorship_goal`, `proposals_count`, `banner_text`, dates, open/closed flags all on `Conference` | These values genuinely differ per year. Avoids module-level constants that require a code deploy to change. |
| Sponsorship uniqueness | None (no unique constraint) | `SponsorshipProfile` is a CRM pipeline; multiple rows per org per year are legitimate (rejected → re-engaged, multiple deal threads). |
| CoC/ToS | Stay as global flags on `PortalProfile` | Once accepted, user is done. Re-prompt only via one-off migration if the text changes substantively. |
| Returning volunteer flow | Form pre-fills from most recent prior `VolunteerProfile` | Lowest friction for returning contributors, with explicit consent preserved (they still submit the form). |
| Previous-event choices | Derived from `Conference` rows; backfill 2023 and 2024 | Zero ongoing maintenance. Choice list grows as conferences are added. |
| Auto-create on signup | Removed | A user can volunteer for multiple years; auto-creating one profile no longer makes sense. Volunteering becomes an explicit per-year action. |

---

## Schema

### New: `Conference` (in `portal/`)

```python
class Conference(BaseModel):
    year = PositiveIntegerField(unique=True)
    name = CharField(max_length=100)
    slug = SlugField(unique=True)
    is_active = BooleanField(default=False)
    pretix_event_slug = CharField(max_length=100, blank=True)

    # year-bound config (replaces hardcoded constants)
    sponsorship_goal = DecimalField(max_digits=10, decimal_places=2, default=0)
    donation_goal = DecimalField(max_digits=10, decimal_places=2, default=0)
    proposals_count = PositiveIntegerField(default=0)

    # year-bound state flags
    volunteer_application_open = BooleanField(default=False)
    sponsorship_open = BooleanField(default=False)
    accepting_donations = BooleanField(default=True)

    # optional metadata
    start_date = DateField(null=True, blank=True)
    end_date = DateField(null=True, blank=True)
    banner_text = CharField(max_length=255, blank=True)

    # snapshot of closed-out year metrics (used when no portal data exists,
    # e.g. for 2023 and 2024, and for "freezing" past years)
    historical_snapshot = JSONField(blank=True, default=dict)

    def save(self, *args, **kwargs):
        if self.is_active:
            Conference.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.get(is_active=True)
```

### Models gaining `conference = ForeignKey(Conference)`

| Model | Notes |
|---|---|
| `VolunteerProfile` | Also: `user` changes from `OneToOneField` to `ForeignKey`. Add `unique_together = ("user", "conference")`. |
| `SponsorshipProfile` | No additional uniqueness. |
| `SponsorshipTier` | Tiers and prices change per year. |
| `Team` | Teams re-form per year, leads can change. |
| `IndividualDonation` | Denormalized; donations are also year-bound via `transaction_date`. |
| `PretixOrder` | Resolved from `event_slug` matching `Conference.pretix_event_slug`. |

### Models unchanged (intentionally global)

- `auth.User` — identity, carries across years.
- `PortalProfile` — pronouns, picture, CoC/ToS agreements.
- `Role`, `Language`, `PyladiesChapter` — global vocabularies.

### Field-level changes

- `AttendeeProfile.participated_in_previous_event` — choices derived from
  `Conference.objects.filter(year__lt=current_year)` plus `FIRST_TIME`.
- `portal/constants.py` — delete `SPONSORSHIP_GOAL_AMOUNT`,
  `DONATION_GOAL_AMOUNT`, `HISTORICAL_STATS`, `PROPOSALS_2025_COUNT` after
  values are migrated onto Conference rows.

---

## Behavior changes

### Sign-up

Sign-up creates only the `PortalProfile`. Volunteering is a separate explicit
action ("Apply to volunteer for PyLadiesCon 2026") that creates a per-year
`VolunteerProfile` tied to the active conference. The post-save signal that
auto-created `VolunteerProfile` is removed.

### Returning volunteers

When a returning user applies for a new year, the form pre-fills from their
most recent prior `VolunteerProfile` (social handles, languages, region,
chapter, availability). They review, adjust, submit. `application_status`
resets to `PENDING` for the new year.

### Current-conference context

A context processor exposes the active `Conference` to all templates so the
navbar, banners, and form headers consistently show the right year.

### Stats

Every aggregation function in `portal/common.py` takes a `conference`
parameter and namespaces its cache key by year. The stats page accepts
`?year=` to switch between conferences; defaults to the active conference
when omitted.

A new page at `/stats/comparison/` shows year-over-year charts, iterating
`Conference.objects.order_by("year")`. For each metric, it reads from
`historical_snapshot` if present, otherwise queries live (filtered by
conference).

When `/stats/?year=2024` is requested for a year that predates the portal,
the page renders `historical_snapshot` values with a banner explaining
"Limited data — this conference predates the portal."

---

## Data migration

Backfill in a single data migration:

```python
Conference.objects.create(
    year=2023, name="PyLadiesCon 2023", slug="2023",
    historical_snapshot={
        "registrations": 600, "sponsors": 8, "sponsorship_amount": "10500",
        "donors": 58, "donation_amount": "650",
    },
    proposals_count=164,
)
Conference.objects.create(
    year=2024, name="PyLadiesCon 2024", slug="2024",
    historical_snapshot={
        "registrations": 732, "sponsors": 11, "sponsorship_amount": "10000",
        "donors": 105, "donation_amount": "1520",
    },
    proposals_count=192,
)
conf_2025 = Conference.objects.create(
    year=2025, name="PyLadiesCon 2025", slug="2025",
    is_active=True, proposals_count=194,
    sponsorship_goal=15000, donation_goal=2500,
)
Conference.objects.create(
    year=2026, name="PyLadiesCon 2026", slug="2026",
)

# All existing rows belong to 2025
VolunteerProfile.objects.update(conference=conf_2025)
SponsorshipProfile.objects.update(conference=conf_2025)
SponsorshipTier.objects.update(conference=conf_2025)
Team.objects.update(conference=conf_2025)
IndividualDonation.objects.update(conference=conf_2025)
```

---

## Migration plan (ordered)

1. Add `Conference` model (schema only, no FKs elsewhere).
2. Add nullable `conference` FK to `VolunteerProfile`, `SponsorshipProfile`,
   `SponsorshipTier`, `Team`, `IndividualDonation`, `PretixOrder`.
3. Data migration: create 2023, 2024, 2025 (active), 2026 Conference rows;
   backfill `conference` on all existing rows to 2025. Backfill 2023/2024
   `historical_snapshot` from `portal/constants.py::HISTORICAL_STATS`.
4. Make `conference` non-null on all affected models.
5. `AlterField` on `VolunteerProfile.user` (OneToOne → FK); drop the implicit
   unique constraint; add `unique_together("user", "conference")`.
6. Update admin classes and `django-import-export` resources
   (`VolunteerProfileResource`, `SponsorshipProfileResource`,
   `AttendeeProfileResource`) to include `conference` and filter by it.
7. Remove the post-save signal that auto-creates `VolunteerProfile`.
8. Update views to filter by `Conference.get_active()` and add the
   returning-volunteer pre-fill logic.
9. Refactor `portal/common.py` aggregation functions to accept a `conference`
   parameter and namespace cache keys by year. Update
   `portal/views.py::stats` and `stats_json` to read `?year=`. Add the
   year-switcher dropdown to stats templates.
10. Extract year-over-year comparison to its own page at
    `/stats/comparison/`. Add `historical_snapshot` and `proposals_count`
    handling in the new view. Delete `HISTORICAL_STATS` and
    `PROPOSALS_2025_COUNT` constants. Add admin action "Freeze stats for
    this conference" to snapshot live aggregations into
    `historical_snapshot` when a year wraps up.
11. Add admin action "Clone teams from prior conference" so 2026 teams
    aren't rebuilt by hand.

Step 5 (the OneToOne → FK change) is the riskiest; consider pausing for
review before merging.

---

## Open questions for future work

- **CoC/ToS versioning**: when the text changes substantively, what's the
  re-acceptance trigger? Currently solved by a one-off migration; revisit
  if changes become frequent.
- **Multi-tenant conferences**: out of scope today. If PyLadies ever wants
  to run other branded events through the portal, `Conference` may need to
  become `Event` or gain an `event_type` field.
- **Pretix event slug per conference**: assumes one Pretix event per
  conference. If a year ever spans multiple Pretix events (e.g., separate
  early-bird event), this assumption breaks and `PretixOrder` needs richer
  linkage.