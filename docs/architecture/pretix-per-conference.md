# Pretix Configuration Per Conference (Architecture)

This document describes how the portal's Pretix integration (ticket orders,
attendee demographics, the "Get Your Ticket" link) is configured per
conference edition, so that a new year needs a new row in the portal and no
code deploy. It is the reference for any work that touches
`common/pretix_wrapper.py`, the Pretix webhook, `fetch_pretix_orders`, or the
Pretix fields on `Conference`.

The integration was written for PyLadiesCon 2025 with the organizer, event
slug and API base URL as module constants. `Conference.pretix_event_slug`
exists (see `multi-year-conferences.md`) but nothing reads it on the way in:
the webhook still rejects any event other than the constant, and the
management command still syncs the constant event.

**Status:** Design. Not implemented.

**Last updated:** 2026-09-20

---

## Goals

- Configure a new year's Pretix event through the portal's conference
  settings page, with no code change and no deploy.
- Route incoming orders to the right `Conference` by what the payload says,
  not by what the code assumes.
- Keep the public ticket link on the home page correct for the active
  edition.
- Remove the hardcoded organizer, event slug and API base URL.

## Non-goals

- Storing the Pretix API token or the webhook secret per conference. A Pretix
  team token is organizer-level and covers every event under that organizer,
  so it does not change per year. The webhook secret is a portal-side value.
  Both stay as environment settings. Task 2.7 in `TASKS.md` may revisit this;
  it would need encryption at rest and is not needed for the yearly rollover.
- Moving the demographic question identifiers off constants. See
  "Question identifiers" below.
- Multiple Pretix events per conference (for example a separate early-bird
  event). Still one event per edition.
- The other hardcoded 2025 values in `templates/portal/registration_callout.html`
  (site link, dates). Separate cleanup.

---

## Current state

| Concern | Where it lives today |
|---|---|
| API base URL | `portal/constants.py::BASE_PRETIX_URL` |
| Organizer slug | `common/pretix_wrapper.py::PRETIX_ORG` |
| Event slug | `common/pretix_wrapper.py::PRETIX_EVENT_SLUG`, and `Conference.pretix_event_slug` (only used to backfill `PretixOrder.conference`) |
| Public ticket link | Literal URL in `registration_callout.html` |
| API token, webhook secret | `PRETIX_API_TOKEN`, `PRETIX_WEBHOOK_SECRET` env settings |

The webhook (`webhooks/views.py`) returns 400 for any payload whose organizer
or event does not equal the constants. `PretixOrder.resolve_conference` matches
the slug to a conference and falls back to the active one when nothing
matches.

---

## Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Where the config lives | On `Conference`, next to the existing `pretix_event_slug` | Attendee stats, the home page and the speaker module all key off `Conference`; a separate settings model would just be a second row to keep in sync. |
| Shape of the config | Three components: instance URL, organizer slug, event slug | Both the shop URL and the API root derive from them. One pasted URL would need parsing and could not express the API base cleanly. |
| Defaults | `https://pretix.eu/` and `pyladiescon` as field defaults | Existing rows (and test fixtures) are correct without a data migration. Only the event slug is genuinely per-year. |
| Unknown organizer or event in a webhook | Log and return 200 with an "ignored" body | Not an error on our side. Pretix retries non-2xx responses, and an organizer-level webhook legitimately delivers events the portal does not track. |
| Active-conference fallback when resolving an order | Removed | It was a bridge for the backfill. With per-edition config it would silently file an unknown event's orders under the current year. |
| Secrets | Stay in the environment | See Non-goals. |

---

## Schema

Two fields added to `Conference` beside `pretix_event_slug`:

```python
class Conference(BaseModel):
    ...
    pretix_base_url = URLField(blank=True, default="https://pretix.eu/")
    pretix_organizer = CharField(max_length=100, blank=True, default="pyladiescon")
    pretix_event_slug = CharField(max_length=100, blank=True)  # existing
```

Derived properties, all on the model so templates, the wrapper and the
webhook share one definition:

```python
@property
def pretix_configured(self) -> bool:
    """All three coordinates are set."""

@property
def pretix_shop_url(self) -> str:
    """Public ticket page: <base>/<organizer>/<event>/. Empty when unconfigured."""

@property
def pretix_api_url(self) -> str:
    """API root for this edition: <base>/api/v1/organizers/<organizer>/events/<event>/."""
```

One schema migration in `portal`. No data migration: defaults cover the
existing rows, and the 2025 row already has its slug.

---

## Consumers

### Pretix wrapper (`common/pretix_wrapper.py`)

- Constructor takes a `Conference`, not two strings. Raises `ValueError` if
  `pretix_configured` is false or the API token is unset.
- URLs come from `conference.pretix_api_url`.
- Keep the status and webhook action constants. Delete `PRETIX_ORG`,
  `PRETIX_EVENT_SLUG` and `portal.constants.BASE_PRETIX_URL`.

### Webhook (`webhooks/views.py`)

Endpoint and secret check unchanged. Payload handling becomes:

1. Validate the payload shape and the action, as today.
2. Look up the conference whose `pretix_organizer` and `pretix_event_slug`
   equal the payload's `organizer` and `event`.
3. No match: log at info level, return 200 with `{"ignored": "unknown event"}`.
4. Match: build the wrapper for that conference, fetch the order by code,
   upsert `PretixOrder` with `conference` set explicitly, then the
   `AttendeeProfile` for paid orders, as today.

Because routing is by payload, the Pretix side is configured once: an
organizer-level webhook for all events. A new year's event starts delivering
as soon as it exists in Pretix, and the portal starts accepting those
deliveries as soon as an organizer fills in the slug on the conference row.

### Order model (`attendee/models.py`)

- The caller assigns `conference` when it creates the row.
  `from_pretix_data` stops re-resolving it and keeps writing `event_slug` for
  reference.
- `resolve_conference` is deleted along with its active fallback.

### Management command (`fetch_pretix_orders`)

- `--conference <year|slug>`: which edition to sync. Defaults to the active
  conference.
- `--all`: sync every conference with `pretix_configured` true. For one-time
  backfills.
- A clear error when the chosen conference is not configured.

### Home page (`templates/portal/registration_callout.html`)

The ticket button links to `active_conference.pretix_shop_url` and is not
rendered when `pretix_configured` is false.

### Forms and views (`portal/forms.py`, `portal/views.py`)

- `ConferenceForm` gains `pretix_base_url` and `pretix_organizer`. The
  template shows the derived shop URL read-only under the fields so an
  organizer can eyeball it.
- The start-next-year form copies `pretix_base_url` and `pretix_organizer`
  from the previous edition and prefills `pretix_event_slug` with the new
  year, matching the naming used so far (`"2025"`).

### Question identifiers

The demographic question identifiers in `attendee/models.py`
(`PRETIX_ATTENDEE_*_QUESTION_IDENTIFIER` and the anonymity answers) stay as
constants. Pretix preserves question identifiers when an event is cloned
from a previous one, so they remain valid as long as each year's event is
cloned rather than built from scratch. If that ever changes, they become a
JSON mapping on `Conference` with these constants as the default. Record the
"clone, don't rebuild" rule in the runbook (`TASKS.md` 7.4).

---

## Tests

- Webhook: an order for a 2026 event lands on the 2026 conference when both
  2025 and 2026 rows exist. Unknown organizer or event returns 200 and creates
  nothing. Existing tests stop importing the deleted constants and read the
  fixture conference's fields instead.
- Wrapper: builds the expected shop and API URLs from a conference; refuses an
  unconfigured conference; refuses a missing token.
- Command: syncs the named conference, defaults to the active one, errors on
  an unconfigured one, `--all` skips unconfigured editions.
- Model: the three properties, including blank and trailing-slash handling.
- Views: start-next-year copies organizer and base URL and prefills the slug;
  the callout omits the ticket button when unconfigured.

The suite runs with `--no-migrations`, so the migration is verified by hand:
apply, confirm the 2025 row reads `pretix.eu` / `pyladiescon` / `2025`,
reverse, re-apply.

---

## Rollout (ordered)

Two pull requests, each cut from a freshly fetched `main`:

1. **Conference carries the Pretix config.** Migration, properties,
   `ConferenceForm`, start-next-year copy, callout template. Nothing reads the
   new fields on the ingest path yet, so this merges safely on its own.
2. **Integration reads from Conference.** Wrapper, webhook, order model,
   management command, constant deletion, test rewrites.

After both land, the yearly procedure is: clone the Pretix event, create the
conference in the portal with the new event slug, done. No deploy, and no
change to the Pretix webhook configuration provided it is set at organizer
level.

---

## Open questions for future work

- **Per-conference token.** Only needed if a year ever runs under a different
  Pretix organizer or instance. Would need encryption at rest.
- **Question identifier mapping.** See above; triggered the first time a
  Pretix event is built from scratch instead of cloned.
- **Webhook actions.** Only `order.paid` and `order.canceled` are handled.
  `TASKS.md` 2.7 wants placed, expired and changed as well, plus a nightly
  reconcile using `modified_since`. Both build on this design without
  changing it.
