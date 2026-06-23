# Multi-Year Conferences — Implementation Progress

Tracking the rollout of the design described in
[`multi-year-conferences.md`](./multi-year-conferences.md).

This file is internal project management — update it as work progresses.
Delete it once everything is done; the design doc preserves the "why".

**Last updated:** 2026-06-13

---

## Status legend

- [ ] Not started
- [~] In progress
- [x] Done
- [!] Blocked or needs attention

---

## Phase 1 — Conference model

- [x] Add `Conference` model to `portal/` with all fields from the design.
- [x] Migration 1: create `Conference` table.
- [x] Add `Conference` to Django admin with `is_active` toggle.
- [x] Implement `Conference.get_active()` and the single-active-row enforcer
      in `save()`.
- [x] Add context processor exposing the active conference to all templates.

## Phase 2 — Foreign keys (nullable)

- [x] Add nullable `conference` FK to `VolunteerProfile`.
- [x] Add nullable `conference` FK to `SponsorshipProfile`.
- [x] Add nullable `conference` FK to `SponsorshipTier`.
- [x] Add nullable `conference` FK to `Team`.
- [x] Add nullable `conference` FK to `IndividualDonation`.
- [x] Add nullable `conference` FK to `PretixOrder`.

Note: `BaseModel` is concrete (multi-table inheritance), so `Conference`
needed an explicit `basemodel_ptr` parent link with `related_name="+"` —
otherwise the implicit reverse accessor named `conference` on `BaseModel`
clashes with the FK name on every child model (`portal` migration 0004).

## Phase 3 — Backfill

All four steps land in one reversible data migration,
`portal/migrations/0005_backfill_conferences.py`.

- [x] Data migration: create Conference rows for 2023, 2024, 2025 (active),
      2026.
- [x] Data migration: backfill `historical_snapshot` for 2023 and 2024 from
      `portal/constants.py::HISTORICAL_STATS`.
- [x] Data migration: backfill `conference` on all existing
      `VolunteerProfile`, `SponsorshipProfile`, `SponsorshipTier`, `Team`,
      `IndividualDonation` rows to point at 2025.
- [x] Data migration: backfill `PretixOrder.conference` from `event_slug`
      matching `Conference.pretix_event_slug`.

Notes:
- Historical values (`HISTORICAL_STATS`, `PROPOSALS_2025_COUNT`, goal amounts)
  are copied literally into the migration, not imported from
  `portal.constants` — a data migration must stay replayable on a fresh DB,
  and Phase 8 deletes those constants. `proposals` is stored on
  `proposals_count`; the rest of each year's stats go in `historical_snapshot`.
- `pretix_event_slug` for 2025 is `"2025"` (matches
  `common.pretix_wrapper.PRETIX_EVENT_SLUG`); orders backfill by slug match so
  future years route automatically.
- Not unit-tested, matching the existing `volunteer/0011_populate_languages`
  convention. The suite runs `--no-migrations`, so data migrations never
  execute under test and are invisible to the 100% coverage gate. Verified
  manually instead: forward + reverse + re-apply against real data.

## Phase 4 — Tighten constraints

- [x] Make `conference` non-null on all affected models
      (`volunteer/0014`, `sponsorship/0010`, `attendee/0005`).
- [x] Change `VolunteerProfile.user` from `OneToOneField` to `ForeignKey`.
- [x] Add `unique_together = ("user", "conference")` to `VolunteerProfile`.
- [ ] Pause for review before merging — riskiest step.

Notes:
- Non-null forced the creation paths to assign a conference now, not later:
  volunteer/sponsorship forms use `Conference.get_active()`; the pretix
  webhook and `fetch_pretix_orders` resolve it via
  `PretixOrder.resolve_conference(event_slug)` (slug match, active fallback);
  `generate_sample_data` seeds and scopes to an active 2025 edition.
- Caught a regression: the `SponsorshipProfileResource` CSV import silently
  failed the new non-null FK — fixed in `before_save_instance` (assigns the
  active conference). The `VolunteerProfileResource` import was already
  vacuous (its `user__*` rows don't persist), so it's deferred to Phase 5.
- Admin visibility added early (subset of Phase 5): `conference` column +
  list filter on every affected model's admin; `Team` gained a `ModelAdmin`;
  `SponsorshipProfileAdmin.fields` now includes `conference`.
- Tests: autouse `conference` fixture in `conftest.py` (skips
  `unittest.TestCase` classes, which seed their own). 372 pass, 100% cov.

## Phase 5 — Admin and import/export

- [x] Add `conference` to `VolunteerProfileResource`, default list filter
      to active conference.
- [x] Add `conference` to `SponsorshipProfileResource`, default list filter
      to active conference.
- [x] Add `conference` to `AttendeeProfileResource` (export-only, via
      `order.conference`).
- [x] Verify existing CSV exports still work and gain a `conference` column.

Notes:
- `conference` is exported/imported by **year** (via `ForeignKeyWidget`),
  not the surrogate pk. Rows imported without a conference column fall back
  to the active edition in `before_save_instance` (this also completes the
  `VolunteerProfileResource` import fix deferred from Phase 4).
- "Default list filter to active" is a reusable `ActiveConferenceFilter`
  (`portal/admin_filters.py`): the changelist lands on the active edition
  with no query param; `?conference=all` shows every year. Applied to the
  volunteer and sponsorship profile admins.
- Admin column/filter visibility on all six models landed in Phase 4.
- Tests: 381 pass, 100% cov; no schema change (admin-only).

## Phase 6 — Behavior changes

- [x] ~~Remove the post-save signal that auto-creates `VolunteerProfile` on
      user signup.~~ N/A — no such signal exists; signup only creates
      `PortalProfile` and volunteering is already explicit via
      `VolunteerProfileCreate`.
- [x] Update "Apply to volunteer" view: explicit action, ties new
      `VolunteerProfile` to active conference. (Conference assignment landed in
      Phase 4; the "already applied?" guard is now scoped to the active
      conference so returning volunteers can apply each year.)
- [x] Implement returning-volunteer pre-fill (form initial values come from
      user's most recent prior `VolunteerProfile`).
- [x] Update volunteer list view to filter by active conference; add an
      admin-only year switcher.
- [x] Update sponsorship list view to filter by active conference.

Notes:
- Multi-year broke several single-profile assumptions, now scoped to the
  active conference: `volunteer index` (`get()` → `MultipleObjectsReturned`),
  the apply guard, and the `portal` dashboard lookup.
- Sponsor access is per-approved-year: staff/superusers see every conference;
  other users may only view the conference(s) they were APPROVED volunteers
  for. `SponsorshipProfileList` defaults to the active edition (or their most
  recent viewable year) with a year switcher; the detail view checks the
  specific sponsor's year.
- Year switchers are a button group on both manage lists; the search form
  carries the selected year in a hidden field. 386 tests pass, 100% cov.

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
- [ ] Admin action: "Bring forward returning volunteers" (issue #333). On the
      `VolunteerProfile` changelist (or `Conference`), select prior-year
      volunteers and create new `VolunteerProfile` rows for the active
      conference, copying profile fields (social handles, languages, region,
      chapter, availability) and optionally team/role assignments. New rows
      land as `PENDING` by default. This is the admin-initiated counterpart to
      the self-service returning-volunteer pre-fill in Phase 6: #333 wants the
      organizer to onboard last year's volunteers into this year's teams
      *without* the volunteer re-filling the form. Depends on the team-clone
      action above (teams must exist in the new year before assignment).
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

## Phase 12 — Organizer "Start a new year" wizard (issue #341)

A guided front-end flow (on the portal dashboard, **not** Django admin) for
organizers who aren't comfortable in Django admin, so standing up next year's
conference isn't a series of manual admin edits.

- [ ] Dashboard entry point (staff/superuser): "Start next year's conference".
- [ ] Step 1 — create: year, name, slug.
- [ ] Step 2 — choose carry-over: teams (Phase 9 clone), sponsorship tiers,
      goal amounts, returning volunteers (#333).
- [ ] Step 3 — review & activate (flip `is_active`; single-active enforcer
      demotes the current year).
- [ ] Implement the team-clone (Phase 9) and volunteer carry-forward (#333)
      as reusable services callable from both Django admin and this wizard, so
      the logic isn't duplicated.

Composes Phase 9's "Clone teams" and #333's "Bring forward returning
volunteers" into one organizer-facing flow; depends on both.

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