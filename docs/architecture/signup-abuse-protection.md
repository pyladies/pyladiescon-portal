# Signup Abuse Protection (Architecture)

This document explains why the public signup form has a CAPTCHA and the
companion controls around it.

**Last updated:** 2026-09-11

**Incident issue:** [pyladies/pyladiescon-portal#406](https://github.com/pyladies/pyladiescon-portal/issues/406)

---

## Why we have it

### What happened

From 2026-05-16 to 2026-07-24 a bot drove the signup form at roughly one
signup every half hour, around the clock, and created 2,249 accounts. That was
90.9% of every account the portal had. Not one of them verified its email
address, not one ever logged in, and every username and name was ten random
lowercase letters.

The accounts were not the goal. Each one was registered against a distinct,
real email address belonging to a stranger. Because the portal sends a
verification email on every signup, the attacker was using our form to make
**us** send 2,249 unsolicited emails from a pyladies.com address. This is a
well-known pattern (a "signup bomb" or "subscription bomb"): any open form that
emails an arbitrary address on submit is a free spam relay, and lists of such
forms circulate.

It went unnoticed for four months because the volume was deliberately low.

### Why the existing controls did not stop it

- **CSRF** stops cross-site forgery. A bot that GETs the page first and reads
  the token is not forging anything.
- **Required CoC/ToS checkboxes** are two more POST keys. 100% of the spam rows
  had both ticked.
- **The per-IP rate limit** (django-allauth's default `signup: "20/m/ip"`)
  permits 28,800 signups per IP per day. The attack peaked at 111 per day, in
  total, across all sources. A per-IP limit is the right tool against one
  impatient script and the wrong tool against a patient, distributed one, and
  we should expect the latter: it is the cheaper attack to run.
- **Mandatory email verification** keeps the spam accounts from logging in.
  It does nothing about the email that was the actual payload, because
  verification is what sends the email.

### Why a CAPTCHA

The attacker's cost per signup was one HTTP round trip. Every control above
leaves that cost unchanged. A CAPTCHA is the only control that raises it, and
raising it is what ends the pattern: our form stops being the cheapest relay on
the list and the traffic goes elsewhere.

We considered and rejected, as the *primary* control:

- **Stricter rate limits alone.** Bound the damage from one source; invisible
  to a hundred sources at one request per hour each. Kept as defence in depth.
- **Honeypot field.** Cheap and worth having, but defeated by any bot that
  renders the page or reads the labels, which is now the common case.
- **Requiring an invite or manual approval.** Would work, and would also mean
  nobody can volunteer for PyLadiesCon without an organizer in the loop first.
  The portal exists to reduce that kind of work, not add it.
- **Deleting unverified accounts.** Removes the litter. Does not stop the
  emails, which is the harm.

### Why django-simple-captcha, and not a hosted service

The choice was between a CAPTCHA generated on our own server
([django-simple-captcha](https://pypi.org/project/django-simple-captcha/))
and a hosted one (Cloudflare Turnstile, Google reCAPTCHA, hCaptcha). We use
django-simple-captcha, following the rule that shapes the rest of the
portal: **a third-party service only when it is absolutely needed and no
adequate open-source, self-hosted library exists.** Here one does, so the
hosted options were never in the running as the default.

- **No tracking script on the page.** The portal deliberately runs no
  analytics and sets no third-party cookies. A hosted CAPTCHA puts a script
  from Cloudflare or Google on the signup page and hands them the IP address
  and browser fingerprint of every visitor, which is exactly the kind of
  tracking we tell people we do not do. The image and the audio are generated
  here and served from `/captcha/`; nothing about the challenge loads from
  anywhere else.
- **No external account, no keys.** Nothing to create in a dashboard, nothing
  to rotate, nothing that differs between development, CI and production.
- **No runtime dependency on someone else's uptime.** A hosted CAPTCHA must
  fail closed, so signup is unavailable whenever the provider is.
- **Maintained.** 0.7.0 released 2026-07, Django 4.2+, MIT, Pillow-based (Pillow
  is already a dependency).

The trade-off: text-in-an-image CAPTCHAs are cheap for modern
vision models to solve. django-simple-captcha will not keep out an attacker
who specifically wants in. It does stop the attack we actually had, which was
not specific at all: a bot walking a list of forms that send email for zero
effort. Any CAPTCHA takes us off that list, and the rate limits below bound
what a paid solver can do per address. If a future attack solves it at
volume, the answer is to escalate to a hosted service, not to tune fonts and
noise.

**Escalation path: Cloudflare Turnstile.** Free at our volume, at the cost of the third-party script
above. The switch is a short PR:

- Settings `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` from env; empty keys
  fall back to Cloudflare's published always-pass test keys in `DEBUG` and
  fail a system check otherwise, so an empty key can never silently mean
  "no CAPTCHA".
- A form field whose widget renders `<div class="cf-turnstile"
  data-sitekey=...>` and reads the `cf-turnstile-response` input Cloudflare's
  script injects; `validate()` POSTs the token to
  `https://challenges.cloudflare.com/turnstile/v0/siteverify` with `requests`
  and fails closed on any error.
- The `api.js` script tag in the signup template's `extra_head` block.
- The widget template must live under an app's own `templates/` directory,
  because Django's form renderer does not search the project-level one.

Packages checked on 2026-09-11, for the record:

| Package | Latest release | Django support | Verdict |
|---|---|---|---|
| `django-simple-captcha` 0.7.0 | 2026-07 | 4.2+ | **Chosen.** Self-hosted, maintained |
| `django-turnstile` 0.1.3 | 2026-01 | classifiers stop at 4.0; single maintainer | Too thin to depend on; the field above is ~40 lines anyway |
| `django-recaptcha` 4.1.0 (Torchbox) | 2025-03 | 4.2 to 5.2 | Well maintained, but Google reCAPTCHA only |

---

## How it is implemented

### Package and settings

`requirements-app.txt` pins `django-simple-captcha==0.7.0`; `"captcha"` is in
`INSTALLED_APPS`, and its one migration (the `CaptchaStore` table) runs with
the normal `migrate`.

```python
# portal/settings.py
CAPTCHA_LENGTH = 6
CAPTCHA_FONT_SIZE = 40  # package default is 22, too small to read comfortably
CAPTCHA_IMAGE_SIZE = (320, 90)  # auto-sizing crops rotated glyphs at the edges
CAPTCHA_LETTER_ROTATION = (-20, 20)  # default +/-35 clips tall letters
CAPTCHA_TIMEOUT = 10  # minutes a challenge stays valid; the form is long
CAPTCHA_FLITE_PATH = shutil.which("flite")
# Mixes random noise into each audio file so the audio for a given challenge
# is never byte-identical (no precomputed audio-to-answer lookup).
CAPTCHA_SOX_PATH = shutil.which("sox")
```

Everything else is the package default: random characters, the bundled font,
noise and blur. `flite` and `sox` are installed in the Dockerfile: `flite`
generates the audio alternative to the image, `sox` adds random noise to it so
two requests for the same challenge never produce the same file. Where a
binary is absent the package degrades quietly: no `flite`, no audio link; no
`sox`, unnoised audio.

### URLs

`path("captcha/", include("captcha.urls"))` in `portal/urls.py` serves
`/captcha/image/<key>/` and `/captcha/audio/<key>/` from this server.

### The form field

`CustomSignupForm` in `portal/forms.py` declares `captcha = CaptchaField(...)`
with a comment pointing here. How a request flows:

1. **GET.** Rendering the field creates a `CaptchaStore` row holding a random
   hash key and the expected answer, and renders the image (URL keyed by the
   hash), a hidden `captcha_0` carrying the key, and a text input `captcha_1`
   for the answer.
2. **POST.** The field looks up a row with that key, that answer
   (case-insensitive) and an expiration still in the future, and **deletes
   it**. A solved challenge therefore cannot be replayed. A missing answer is
   "This field is required"; a wrong or stale one is "Invalid CAPTCHA";
   either way no user is created.
3. **Housekeeping.** Every validation prunes expired rows
   (`CaptchaStore.remove_expired()`), so no cleanup job is needed.

### The template

`templates/account/signup.html` renders `{{ form.captcha }}` with its label,
errors and help text immediately above the submit button. It is the last
field so it is not solved long before the user has finished typing.

The widget itself is `PortalCaptchaTextInput` (`portal/forms.py`), the
package widget with one change: its template
(`portal/templates/portal/widgets/captcha.html`) shows the audio alternative
as an inline `<audio controls>` player next to the image, labelled "Or listen
to the characters". The package default makes the image the audio link with
only a hover title, which nobody finds, and a plain link downloads the file
instead of playing it. The player appears only when `CAPTCHA_FLITE_PATH`
resolves; the audio is generated by `flite` on this server and streamed from
`/captcha/audio/<key>.wav` with range support, which is what `<audio>` needs.

### Where it is *not* applied

Login, password reset and email-change forms already carry allauth's
per-account and per-key limits and do not email arbitrary addresses on
demand from anonymous visitors. If any of them ever does, it gets the same
field.

### Tests that guard the control

In `tests/portal/test_captcha.py` and `tests/portal/test_forms.py`. The
`captcha_solution` fixture in `conftest.py` generates a real challenge and
reads the answer back from `CaptchaStore`, so the tests exercise the actual
validation path rather than a test mode.

1. The signup page renders a challenge (`captcha_0`, `captcha_1`, an image
   URL under `/captcha/image/`).
2. The image is served locally as a PNG.
3. A signup POST **without** an answer is rejected and creates no user.
4. A signup POST with a wrong answer is rejected and creates no user.
5. A signup POST with the right answer creates the user.
6. Replaying an already-solved challenge is rejected.
7. `CustomSignupForm` has a `captcha` field (`test_form_has_captcha_field`).
   This is the test that fails if someone removes the field; its docstring
   points at this document.

---

## Companion controls

These do not replace the CAPTCHA and the CAPTCHA does not replace them.

### Rate limits

```python
ACCOUNT_RATE_LIMITS = {
    "signup": "5/h/ip,20/d/ip",
}
```

allauth merges this over its defaults, so every other key keeps its default.
Twenty signups per IP per day is generous for a shared office or conference
Wi-Fi and still bounds one source to a nuisance. The cache backend is the
shared `DatabaseCache`, so the limit is global across gunicorn workers.

### Unverified accounts are ephemeral

`UNVERIFIED_ACCOUNT_RETENTION_DAYS` (env-configurable, default 7) is the
single source of truth for how long an account may sit unverified.

- `portal.adapter.PortalAccountAdapter` injects the value into every allauth
  email context, and the verification email tells the recipient that an
  unverified account is deleted after that many days without notice. Someone
  whose address was submitted by a stranger therefore knows they can ignore
  the email.
- The `delete_unverified_accounts` management command
  (`portal_account/management/commands/`) deletes users who have no verified
  `EmailAddress`, whose `date_joined` is older than the window, who have never
  logged in, and who are neither staff nor superusers. `--dry-run` reports
  the count without deleting; `--days N` overrides the window for one run.
  `portal_account.tasks.delete_unverified_accounts_task` runs the same code
  on a schedule. The schedule lives in the database
  ([django-celery-beat](https://pypi.org/project/django-celery-beat/),
  `CELERY_BEAT_SCHEDULER = DatabaseScheduler`), seeded by the
  `0004_maintenance_setup` migration as the "Delete unverified accounts"
  periodic task at 03:00 UTC daily, and editable in the Django admin under
  *Periodic tasks*, where `last_run_at` and `total_run_count` show whether
  it is firing. The `worker-beat` process in the Procfile has to be running
  for any of this to happen (see [Deployment](../developer/deployment.md)).
  A real person who missed the window simply signs up again.
- Both the command and the task return or print the number deleted, so a
  manual run and a scheduled run leave the same trace (stdout and the Celery
  task result respectively).
- The first run also removes the 2,249 rows from the incident: every one of
  them is unverified, never logged in and long past any window. Run it with
  `--dry-run` first and compare the count with the export.

### The verification email carries no user-supplied text

`templates/account/email/email_confirmation_message.txt` says "someone used
this email address", not "user *username* has given your email address". The
email is `text/plain`, so escaping would change nothing; the fix is to not
reflect attacker-chosen strings into mail sent under our domain at all.

### Detection: the Maintenance section

The incident was four months old when a manual data audit found it. Nothing
was counting. The fix is not an alert (an email per signup is noise for a
single maintainer, and hosted monitoring is a service and a bill this project
does not want) but a number in a place a maintainer already goes.

**Maintenance → Accounts** (`/maintenance/`, `MaintenanceAccountsView` in
`portal_account/views.py`, figures from `portal_account/stats.py`) shows,
computed on request:

- totals: accounts, verified, unverified, never logged in, and **pending
  deletion** (what the next `delete_unverified_accounts` run will remove, so
  the job can be sanity-checked before it runs);
- signups today, last 7 days and last 30 days, each with its verified rate;
- signups per day for the last 30 or 90 days as a stacked verified/unverified
  bar.

During the incident this page would have shown a wall of unverified signups
with a 0% verified rate from the first week. The section is built to take
more pages (a `Jobs` page for the beat tasks is the obvious next one) without
redesign: `templates/portal/_maintenance_rail.html` is its rail.

It is reached from the user menu (the "Welcome" flyout, next to *Admin
Area*) and, for organizers who are also maintainers, from a *Maintenance*
section in the Organize rail. It is deliberately not a top-level nav item:
it is upkeep, not something every visitor should see in the bar.

**Decision: Maintenance is the permanent home for portal-health metrics.**
The Accounts page is the first occupant, not the point. Until now every
number the portal showed was about the conference being organized
(volunteers, sponsors, donations, proposals) and lived on the Organizer
dashboard or the public Stats page. There was nowhere to look at the portal
*itself*, which is why an anomaly in the one metric nobody was showing went
unseen for four months. Going forward:

- Anything that describes the health of the portal rather than the progress
  of a conference goes under Maintenance, behind the maintainer permission.
  Candidates already known: scheduled job runs and their outcomes, signup
  rate-limit hits, email delivery failures, media storage growth, stale
  sessions. Each is its own page in the rail, alongside Accounts.
- Anything about the current edition stays on the Organizer dashboard. The
  test is "would this number still matter if there were no conference this
  year?" If yes, it is Maintenance.
- A new metric arrives with the question it answers written on the page
  (as Accounts does with "pending deletion") and, where it has a threshold,
  the threshold visible next to the number. The reader should not need to
  remember what normal looks like.
- The pages stay read-only and computed on request until a metric is
  expensive enough to need caching. Alerts, if ever, are a later decision
  and not a substitute for the page.

### Roles: maintainer is a permission, not staff

Until this change the portal had one role: `is_staff` (or superuser) meant
"organizer", and that bit also opens the Django admin. Infra pages should not
hang off it: someone who looks after the portal is not necessarily running
the conference, and the reverse.

- **Permission** `portal_account.view_maintenance`, declared on
  `PortalProfile.Meta.permissions`.
- **Group** `Infra maintainers`, created by the `0004_maintenance_setup`
  data migration with that permission attached. Adding a person is a
  checkbox on their user in the Django admin.
- **Check** through `has_perm` only: `portal_account.permissions.is_maintainer`,
  used by `MaintainerRequiredMixin` (`common/mixins.py`) for the views and by
  the `is_maintainer` capability flag for the nav. Never by group name, so a
  permission granted directly or to a superuser counts too.

Organizer and maintainer are independent: a person can hold either or both.
Superusers pass every `has_perm`, so they need no group membership. Making
"organizer" a permission too, so that it stops being the same bit as "can
use the Django admin", is the natural follow-up and is out of scope here.
