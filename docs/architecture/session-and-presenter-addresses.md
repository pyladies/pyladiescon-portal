# Session and Presenter Addresses (Architecture)

This document describes how the speaker portal addresses sessions and
presenters in URLs, why those two are addressed by slug while everything
else keeps a numeric id, who may change a slug and until when, and what a
change breaks. It is the reference for any work that adds a URL under
`/speakers/`, touches `Session.slug` or `Presenter.slug`, or builds a link
to a session or presenter from an email, a calendar feed or the public API.

## Why

The portal replaces a set of Google Sheets whose links were gibberish. Its
own addresses should mean something to the person reading them. There is a
second, quieter reason that decided the question: a numeric id is a
creation counter. `/speakers/sessions/42/` tells a speaker that forty-one
sessions were thought of before theirs, and a low number reads as "first"
or "more important" whether or not anyone intends it. A presenter should
see `/speakers/presenters/ada-lovelace/` and nothing about where they sit
in a sequence.

## Goals

- Every address a speaker or the public can see or share names the thing
  by its slug, never by a number.
- The same slug scheme serves the portal, the public program pages, the
  calendar feeds and the API, so a session has one address everywhere.
- Organizers can correct a slug, with the consequences stated on the form.

## Non-goals

- Hiding ids everywhere. Numbers stay in addresses nobody shares (see
  "Which addresses keep a number").
- Redirecting old slugs. A slug is meant to be stable; if published
  addresses ever have to change, a slug-history table with redirects is the
  follow-up, not a reason to design around it now.
- Global uniqueness across years. Slugs are unique per edition, on purpose.

## Locked decisions

- **Both models carry a `slug`** (`Session.slug`, `Presenter.slug`),
  unique per edition by a database constraint on `(conference, slug)`.
- **Derived once, never rotated.** On first save a blank slug is derived
  from the session title or the presenter's display name (`slugify`,
  truncated to 80 characters, `-2`, `-3` on collision within the edition).
  Renaming the title or the display name afterwards leaves the slug as it
  is, so an edit never silently breaks a link.
- **Organizers may edit a slug** on the session and presenter forms. The
  field accepts free text and normalises it (`Intro To Django` becomes
  `intro-to-django`), refuses the reserved path words that live under
  `/speakers/` (`new`, `edit`, `me`, `sessions`, `presenters`, `settings`
  and the rest, listed in `speakers/forms.py`), refuses a clash within the
  edition, and treats a blank as "keep the current address". The check is
  in the form because the unique constraint spans `conference`, which is
  not a form field, so Django's own constraint validation skips it.
- **Speakers will get the same edit, within a window.** The help text on
  the field already states the policy: the address is public, organizers
  review slugs and may rename them, and the address locks once the session
  is scheduled. Enforcement of that window is the next piece of work
  (task 2.11 in the speaker portal plan); until it lands the text describes
  policy, not a mechanism.
- **Lookups are scoped to the edition.** Every view that resolves a slug
  filters by the active conference first, so `django-101` in 2027 does not
  find the 2026 session, and a slug from another year returns 404.
- **Digits are allowed.** A session titled "2027" gets the slug `2027`.
  That is fine: nothing resolves by number any more, so there is no
  ambiguity to protect against.
- **ASCII only, transliterated.** Addresses are plain ASCII, because a
  unicode address is shown percent-encoded the moment it is copied into a
  chat or an email (`/presenters/%E6%9D%8E%E5%8D%8E/`), which is the
  gibberish this whole decision exists to avoid. Non-Latin names are
  transliterated before slugifying (`text-unidecode`) rather than dropped,
  so 李华 is `/speakers/presenters/li-hua/`, Θεοδώρα is `/theodora/` and
  Zoë Müller is `/zoe-muller/`; nobody gets a numbered placeholder for
  having a name outside the Latin alphabet. A title with no letters at all
  (emoji, punctuation) falls back to `session` or `presenter`, suffixed if
  taken. (Decided 2026-09-21 after a first cut had kept unicode.)
- **Reserved words are enforced where slugs are made.** The derivation
  helper treats a reserved path word as taken, so a session titled "New"
  gets `new-2` and can never shadow the create route; both models also
  refuse a reserved word or a per-edition clash in `clean()`, so the admin
  form reports it rather than the database. The reserved set lives in
  `speakers/constants.py`, and a test walks the URL patterns and fails if a
  literal segment that sits where a slug would is missing from it.
- **The help text says what the code does.** Until the edit windows land,
  the organizer forms say speakers can change a slug until the session is
  scheduled and organizers can always rename it; the lock on the speaker
  side is enforced by the edit-windows change, not by these forms.

## Which addresses keep a number

The test is: would a speaker or the public ever see or share this address?
If not, an id is the simplest correct key and there is nothing to hide.

| Address | Key | Why |
|---|---|---|
| `/speakers/sessions/<slug>/`, `/edit/`, `/presenters/add/` | slug | The session's identity; shared and shown. |
| `/speakers/presenters/<slug>/`, `/edit/`, `/items/add/` | slug | The presenter's identity; shared and shown. |
| `/speakers/me/sessions/<slug>/edit/`, `/suggest/` | slug | What the speaker sees in their own address bar. |
| `/speakers/sessions/<slug>/presenters/<id>/invite/`, `/remove/` | slug + id | The session is the identity; the id names one presenter-on-session link, an organizer action nobody bookmarks. |
| `/speakers/invitations/<token>/` | signed token | The link in the invitation email carries a single-use, expiring token; it must not be guessable, so neither a slug nor an id would do. |
| `/speakers/invitations/<id>/resend/`, `/cancel/` | id | Organizer-only POST actions on an invitation row. |
| `/speakers/items/<id>/status/`, `/assign/`, `/speakers/me/items/<id>/toggle/` | id | Checklist item actions, POST-only, targeted by htmx; the item has no name a person would type. |
| `/speakers/settings/types/<id>/`, `/roles/<id>/`, `/checklists/<id>/...` | id | Organizer settings pages. Types and roles have a `code` (`WORKSHOP`, `PANELIST`) that seeds and next year's copy use, but those pages are not shared and the code is editable until a type is in use. |

The public program pages, calendar feeds and API planned for Stage 5 use
the same slugs, with the edition in the path, so a session's public address
and its portal address share one identifier.

## What a slug change breaks

Nothing inside the portal: every relation uses the integer primary key, so
checklists, invitations, the activity log and the schedule keep working. The
damage is to links that already exist outside the database:

- Bookmarks, links pasted into Discord or email, and any open tab.
- Once Stage 5 lands, the public program page, the session's calendar file
  and a presenter's calendar subscription, plus anything indexed or shared
  on social media.

The invitation email is unaffected, since it links by token. This is why the
form says that links already shared break, why organizers review slugs, and
why the address locks once the schedule is confirmed.

## Tests

`tests/speakers/test_session_views.py` (`TestSlugUrls`) and
`tests/speakers/test_presenter_views.py` (`TestPresenterSlugUrls`) cover:
absolute URLs contain no digit; same title or name within an edition gets a
suffix; a rename keeps the slug; a slug from another edition and an unknown
slug both 404; an organizer editing a slug gets a clash and a reserved word
refused, free text normalised, and a blank left as the current address; and
the help text renders on both edit pages.
