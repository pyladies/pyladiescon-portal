# Multi-Year Conferences — Implementation Progress

Tracking the rollout of the design described in
[`multi-year-conferences.md`](./multi-year-conferences.md).

This file is internal project management — update it as work progresses.
Delete it once everything is done; the design doc preserves the "why".

**Last updated:** 2026-05-11

---

## Status legend

- [ ] Not started
- [~] In progress
- [x] Done
- [!] Blocked or needs attention

---

## Phase 1 — Conference model

- [ ] Add `Conference` model to `portal/` with all fields from the design.
- [ ] Migration 1: create `Conference` table.
- [ ] Add `Conference` to Django admin with `is_active` toggle.
- [ ] Implement `Conference.get_active()` and the single-active-row enforcer
      in `save()`.
- [ ] Add context processor exposing the active conference to all templates.

## Phase 2 — Foreign keys (nullable)

- [ ] Add nullable `conference` FK to `VolunteerProfile`.
- [ ] Add nullable `conference` FK to `SponsorshipProfile`.
- [ ] Add nullable `conference` FK to `SponsorshipTier`.
- [ ] Add nullable `conference` FK to `Team`.
- [ ] Add nullable `conference` FK to `IndividualDonation`.
- [ ] Add nullable `conference` FK to `PretixOrder`.

## Phase 3 — Backfill

- [ ] Data migration: create Conference rows for 2023, 2024, 2025 (active),
      2026.
- [ ] Data migration: backfill `historical_snapshot` for 2023 and 2024 from
      `portal/constants.py::HISTORICAL_STATS`.
- [ ] Data migration: backfill `conference` on all existing
      `VolunteerProfile`, `SponsorshipProfile`, `SponsorshipTier`, `Team`,
      `IndividualDonation` rows to point at 2025.
- [ ] Data migration: backfill `PretixOrder.conference` from `event_slug`
      matching `Conference.pretix_event_slug`.

## Phase 4 — Tighten constraints

- [ ] Make `conference` non-null on all affected models.
- [ ] Change `VolunteerProfile.user` from `OneToOneField` to `ForeignKey`.
- [ ] Add `unique_together = ("user", "conference")` to `VolunteerProfile`.
- [ ] Pause for review before merging — riskiest step.

## Phase 5 — Admin and import/export

- [ ] Add `conference` to `VolunteerProfileResource`, default list filter
      to active conference.
- [ ] Add `conference` to `SponsorshipProfileResource`, default list filter
      to active conference.
- [ ] Add `conference` to `AttendeeProfileResource`.
- [ ] Verify existing CSV exports still work and gain a `conference` column.

## Phase 6 — Behavior changes

- [ ] Remove the post-save signal that auto-creates `VolunteerProfile` on
      user signup.
- [ ] Update "Apply to volunteer" view: explicit action, ties new
      `VolunteerProfile` to active conference.
- [ ] Implement returning-volunteer pre-fill (form initial values come from
      user's most recent prior `VolunteerProfile`).
- [ ] Update volunteer list view to filter by active conference; add an
      admin-only year switcher.
- [ ] Update sponsorship list view to filter by active conference.

## Phase 7 — Stats refactor

- [ ] Refactor every aggregation function in `portal/common.py` to accept a
      `conference` parameter.
- [ ] Namespace stats cache keys by year (e.g.,
      `volunteer_signups_count_2025`).
- [ ] Update `portal/views.py::stats` and `stats_json` to read `?year=`.
- [ ] Add year-switcher dropdown to `templates/portal/stats.html`.
- [ ] Add year-switcher to `volunteer_stats.html`,
      `sponsorship_stats.html`, `attendee_stats.html`.
- [ ] Handle "predates the portal" case: render `historical_snapshot` with
      a banner when live data is empty.

## Phase 8 — Year-over-year comparison page

- [ ] Add `historical_snapshot` and `proposals_count` fields to `Conference`.
- [ ] Migrate `HISTORICAL_STATS` and `PROPOSALS_2025_COUNT` values into
      Conference rows.
- [ ] Add new view `stats_comparison` at `/stats/comparison/`.
- [ ] Add new JSON endpoint at `/stats/comparison.json`.
- [ ] Build template `portal/stats_comparison.html` with the 7 year-over-year
      charts.
- [ ] Remove `{% include "portal/historical_comparison_charts.html" %}` from
      `stats.html`.
- [ ] Delete `HISTORICAL_STATS` and `PROPOSALS_2025_COUNT` from
      `portal/constants.py`.
- [ ] Delete `get_historical_comparison_data()` from `portal/common.py`.

## Phase 9 — Admin actions and polish

- [ ] Admin action: "Clone teams from prior conference" on `Conference`.
- [ ] Admin action: "Freeze stats for this conference" — snapshot live
      aggregations into `historical_snapshot`.
- [ ] Update `AttendeeProfile.participated_in_previous_event` choices to
      derive from `Conference.objects.filter(year__lt=current_year)`.
- [ ] Add navbar year indicator showing the active conference name.

## Phase 10 — "Your Conferences" history view

- [ ] Add a section to the user's profile/account page listing every
      `VolunteerProfile` the user has across all conferences, ordered by
      most recent year first.
- [ ] Each row shows: conference name, year, `application_status`, link to
      that year's profile detail page.
- [ ] Empty-state copy when the user has no `VolunteerProfile` rows yet.
- [ ] Equivalent listing for `SponsorshipProfile` entries linked to the
      user (via `user`, `main_contact_user`, or `additional_contacts`).

## Phase 11 — Verification

- [ ] All existing tests pass.
- [ ] New tests for `Conference` model (single-active enforcer,
      `get_active()`).
- [ ] New tests for returning-volunteer pre-fill flow.
- [ ] New tests for year-aware stats aggregation.
- [ ] Manual QA: create 2026 conference, flip `is_active`, verify stats and
      volunteer flow.
- [ ] Manual QA: switch back to 2025 via `?year=2025`, verify historical
      data renders correctly.
- [ ] Manual QA: visit `/stats/comparison/`, verify 2023–2026 all render
      with appropriate data sources.

---

## Open items / blockers

(None yet — populate as issues come up.)

## Related branches

The following pre-existing branches may need rebasing onto this work:

- `feature/stats-comparison-charts-287`
- `feature/attendee-stats-276`
- `display-attendee-stats`
- `tabs-for-stats`
- `expose-stats-json`