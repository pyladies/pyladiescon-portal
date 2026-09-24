# Speakers app

The speaker portal for PyLadiesCon: sessions, presenters, invitations,
checklists, scheduling, media pipeline and the public program. The design is
`docs/architecture/speaker-portal.md` on the docs site; the task breakdown
that drives the build is kept by the maintainer outside the repository. This
file records how the existing portal works, with file paths, and the
conventions this module follows so every task session starts from the same
map.

## The portal as it is

### Tenancy: `Conference` is the "Project"

The design document scopes everything to a `Project`. In this portal that
tenant already exists and is called `Conference` (`portal/models.py`,
`class Conference`). One row per edition, `year` and `slug` unique, exactly one
row `is_active=True` at a time (enforced in `Conference.save()`), read through
`Conference.get_active()`. Year-bound configuration (goals, open/closed flags,
external links) lives on that row. `docs/architecture/multi-year-conferences.md`
is the locked design; `multi-year-progress.md` next to it tracks the rollout.

Every year-bound model carries `conference = ForeignKey("portal.Conference",
on_delete=PROTECT, related_name=...)`, for example `volunteer.Team` and
`volunteer.VolunteerProfile` (`volunteer/models.py`) and the sponsorship models
(`sponsorship/models.py`). Admin changelists default to the active edition via
`portal.admin_filters.ActiveConferenceFilter`. There is no tenant middleware:
views resolve the edition with `Conference.get_active()` and filter
explicitly, and the tests' autouse `conference` fixture (`conftest.py`) seeds
one active 2025 edition per test.

In this app the tenant FK is named `conference`, never `project`.

### Base model

`portal.models.BaseModel` adds `creation_date` and `modified_date`. It is a
concrete model (multi-table inheritance, not abstract), which gives it a
reverse accessor named after every child model (`basemodel.role`,
`basemodel.language`, `basemodel.session`...) and a join on every query.
`portal.Conference` already works around the accessor clash with
`related_name="+"`. The speakers models need fields called `session`,
`presenter`, `role` and `language`, so they use their own abstract
`speakers.models.TimestampedModel` with the same two fields instead.

### Users, permissions and groups

- Accounts are `django.contrib.auth.User` via django-allauth
  (`portal/settings.py`: `ACCOUNT_*`, login by username, mandatory email
  verification by code, custom signup form in `portal/forms.py`, adapter in
  `portal/adapter.py`). Passwordless sign-in is allauth's login-by-code
  (`ACCOUNT_LOGIN_BY_CODE_ENABLED`, templates already in `templates/account/`):
  presenters get an account with no password when they accept an invitation
  and sign in afterwards with an emailed code.
- `portal_account.PortalProfile` (`portal_account/models.py`) is the one
  per-user profile: pronouns, picture, CoC/ToS flags. It is global, not
  per-edition.
- "Organizer" means `user.is_superuser or user.is_staff`:
  `common.mixins.AdminRequiredMixin` (`common/mixins.py`) and the
  `is_organizer` flag from `portal.context_processors.user_capabilities`
  (`portal/context_processors.py`), which every template receives.
- Finer capabilities go through Django permissions, granted by groups and read
  with `has_perm`: `portal_account/permissions.py` (`is_maintainer`) is the
  reference shape, and `common.mixins.MaintainerRequiredMixin` gates the view.
  Object-level access is a data check (`TeamLeadRequiredMixin` looks at
  `team.team_leads`), which is the pattern liaison scoping follows.
- Volunteers are `volunteer.VolunteerProfile` rows per edition with
  `Role`s (`volunteer/constants.py`, `RoleTypes`) and `Team`s. Internal
  notification emails go to admin/staff role holders (`sponsorship/tasks.py`,
  `send_internal_email_task`).

### Activity log

There was no `ActivityLog` model in the portal before this app.
`speakers.ActivityLog` (`speakers/models.py`) is edition-scoped, points at any
speakers record through a generic foreign key, and has a nullable `actor` so
automatic events ("pretix order paid, registration marked done") are told
apart from things a person did. Write through `ActivityLog.record(...)`, read
with `ActivityLog.for_target(obj)`.

### The volunteer app (nearest existing pattern)

The design's "volunteer tasks" is the `volunteer` app: `volunteer/models.py`
(`Team`, `Role`, `VolunteerProfile`, `Language`, `PyladiesChapter`),
`volunteer/views.py` (django-filter `FilterSet` + django-tables2 tables for
lists, class-based create/update/detail views, `LoginRequiredMixin` and the
`common.mixins` mixins for access), `volunteer/forms.py`, `volunteer/admin.py`
(django-import-export resources, `ActiveConferenceFilter`), `volunteer/tasks.py`
(Celery tasks that send email), and `volunteer/urls.py` under the `volunteer:`
namespace. Templates are in the repo-level `templates/volunteer/`. The list
table template is `portal/base-tables-responsive.html`
(`DJANGO_TABLES2_TEMPLATE`).

### Storage

`portal/settings.py`: local `FileSystemStorage` under `media/` by default;
with `USE_SPACES=true` the default storage is
`storage_backend.custom_storage.MediaStorage` (`storage_backend/custom_storage.py`,
django-storages `S3Boto3Storage`, `location="media"`, no overwrite) against
Digital Ocean Spaces through the `AWS_*` env vars, with `AWS_DEFAULT_ACL =
"public-read"` and unsigned URLs. Existing uploads are `ImageField`s
(`PortalProfile.profile_picture`, `PyladiesChapter.logo`). There is no private
bucket or presigned-URL code yet; Stage 1.5 and 4.1 add it.

### Secrets at rest

`speakers/encryption.py` provides `EncryptedTextField` (Fernet), used for the
pretix API token and webhook secret on `SpeakerSettings`. Keys come from the
`FERNET_KEYS` environment variable (comma-separated: the first encrypts,
every key decrypts, so rotate by putting the new key first, deploying,
re-saving the secrets, then dropping the old key) or the single `FERNET_KEY`;
local development and the test suite derive one from `SECRET_KEY`. Production
must set one (generate with `Fernet.generate_key()`), or saving those fields
raises. Reading is forgiving: a row this deploy cannot decrypt loads as
`encryption.Undecryptable` (falsy, logged once) instead of raising, so a
missing key degrades pretix to "not configured" rather than taking every page
that loads `SpeakerSettings` down with it; `pretix_configured` and the webhook
treat it as absent, and saving it back is refused. The admin never renders the
secrets; leave the field blank to keep the stored value.

### Pretix

Orders live in `attendee.PretixOrder` (per edition, resolved from the pretix
event slug). The attendee app has its own global webhook
(`webhooks/views.py`, hardcoded organizer and event); the speaker portal
adds a per-edition receiver at `/speakers/webhooks/pretix/<slug>/?secret=`
(`speakers/webhooks.py`) that re-fetches the order through
`speakers/pretix.py` (`PretixClient` with pagination and retry) and upserts
it with the attendee app's own field mapping, so both paths agree. Nightly
`pretix_reconcile_task` pages through `modified_since` the last run.
`Presenter.pretix_order` is the manual link that wins over email matching.

### Item ownership

An organizer checklist item is owned by a person (`assignee`) or by a
`volunteer.Team` (`team`), never both; `assign_item()` enforces it and
`ChecklistItem.owner_label` renders whichever is set. Template lines can
start an item unassigned, with the presenter's liaison, or with a named
team (`default_team_name`, matched by name per edition so templates clone
forward). "My volunteering tasks" shows items assigned to me or to a team I
am an approved member of, by due date or grouped by presenter, with the same
rows as the speaker checklist; team reminders go to every approved member.
It sits under the personal "My volunteering" rail for everyone, organizers
included, because it is a person's own work rather than a view of the
edition, and the Organize rail no longer carries it. A volunteer who is
neither an organizer nor a liaison sees the entry once something is assigned
to them or their team, and may mark those items done and reopen one they
closed too early. Reassigning stays with organizers, and
skipping an item, which is a judgement that it does not apply and carries a
note that may be internal, stays with organizers and liaisons
(`permissions.owned_by` decides who carries an item; `can_work_queue`
decides who reaches the page, and the same predicate puts the entry on the
rail).

`speakers/stats.py` feeds three places from the same numbers: a person's own
tally on the volunteer hub, the edition's on the organizer dashboard, and
overall totals on the public stats page and its JSON, cached like the other
public stats and absent when the module is off.

A note on an item is written by whoever changed its status. The presenter
reads it only when the item is blocked, on their checklist and on the item
page alike: a blocked note explains a hold-up they need to know about, while
a skip note is a conversation among organizers.

### Proposals, and speakers adding their own sessions

An edition can open the door: while `SpeakerSettings.proposals_open` is on,
anyone with a portal account proposes a session at `/speakers/propose/`, and
a speaker already on the program adds one without review. Only session types
with `open_for_proposals` are offered, so nobody proposes a coffee break.

A proposal is real rows from the start: a `Presenter` with the account
linked, a `Session` in `PROPOSED`, an unconfirmed `SessionPresenter`, and a
`Proposal` carrying the review. Approving runs the acceptance path an
invitation takes (`services.approve_proposal`), so the checklists, the
confirmation and the emails are the ones a speaker always gets, dated from
the approval. Rejecting keeps the rows and locks the session's identity, and an
organizer can still approve it afterwards: slots open up when something is
cancelled, and the whole acceptance path runs then, dated from the second
answer.
Withdrawing, while nobody has answered, keeps both rows and takes them off
the organizers' list: withdrawing usually means "not like this" rather than
"forget it", so the writing stays, the proposer can keep editing it, and
"Send it again" puts it back in the queue as a fresh pending proposal.

A speaker who is already on the program skips all of that: `add_own_session`
creates a `DRAFT` with them confirmed on it and their checklist started, and
tells the organizers and their liaison. A draft is not public and not
scheduled, so organizers keep the program.

Both are capped per presenter per edition (`MAX_PENDING_PROPOSALS`,
`MAX_SELF_SESSIONS`), and `Session.created_by_presenter` marks what came in
this way.

`Presenter.is_onboarded` is what the speaker area gates on, rather than the
presenter row existing: a proposer has a row before anyone has said yes.

### Items nobody can start yet (readiness)

An item exists long before it can be done: confirming a slot before the
schedule is built, reading a guide nobody has published, a tech check the
team has not opened booking for. Such an item **waits**. It stays in place
on the list, muted, with one line saying what it waits for, and
`set_item_status` refuses a manual tick, so the disabled box is not the
only guard.

A template line waits on any of three sources, and an organizer override
outranks all of them (`speakers/readiness.py`):

- **A rule** (`ready_rule`), for something the database can answer:
  `session_scheduled`, `guide_published`, `registration_open`. Adding one is
  a code change, because the predicate is code.
- **A gate** (`ready_gate_code`), a switch organizers flip on the
  "Readiness gates" page, for work the portal cannot see: the tech check
  equipment, an upload feature that does not exist yet. One flip opens every
  item waiting on it, and adding a gate is data rather than a deploy. The
  item carries the **code**, and the gate row is resolved from it, so a gate
  created later attaches to the items that already named it and deleting one
  puts those items back to waiting. A code the edition has no gate for waits
  too: it names work nobody has recorded. Gates fail shut in every
  direction, on purpose.
- **Another line** (`waits_for`), for the one piece of work that unblocks
  this one, which is how a speaker line waits on the organizer line behind
  it. The instance link is resolved from the line, since the blocking item
  may be created later.
- **The override** (`ready_override`, organizer-only): open this item
  whatever it waits for, or hold it shut whatever it does not. A held item
  tells the speaker that the organizers are holding it, rather than
  repeating a reason that is no longer the one that matters, and the
  activity log says who decided.

A finished item never waits, whatever its sources say: shutting a gate
again must not drag done work back into the waiting count, where the
progress line would hold it twice.

The answer is stored on the item (`is_waiting`, `waiting_reason`) so the
digests and the counts can filter in SQL. It is refreshed when a gate flips,
when a blocking item is finished or reopened, when an item is created, and
nightly alongside the auto-completion rules. A batch of new items is
evaluated once more when the batch is complete, since a line may wait on one
that sorts after it, whose item does not exist yet as the first one is
made. A line may not wait on itself through others; `clean()` refuses the
cycle where the person making it can see what they did.

A waiting item is **counted but never chased**: it is in "3 of 12 done, 2
waiting", and it is left out of the overdue count, the digests and the
reminder emails. Gates clone into next year shut, since last year's answer
says nothing about this year's work.

### General items (once per presenter)

Templates have three scopes. `GENERAL` ("Every presenter", one per edition,
no kind/role/delivery) is instantiated once per presenter when they first
accept, with `session=None` items: bio, guide, registration, Discord and
the organizer's onboarding lines. `PRESENTER` templates keep per-session
lines; a line marked `once_per_presenter` (the kind-specific guides) also
creates one session-less item per presenter, whatever the number of
sessions. General items live in the speaker's "For you as a speaker"
group and never on a session page; the dashboard shows their completion.
Loading the defaults (or `manage.py dedupe_general_items`) collapses the
per-session copies an edition seeded before this change still carries
(`collapse_general_duplicates`). The tech check is general too.

### Template changes reach existing checklists

There is no back-fill step. Adding a template line creates the item on
every checklist already made from that template (`apply_new_template_item`),
editing a line updates its instances (`apply_template_item_changes`: title,
description, recomputed due date, flags and rule; order silently), deleting
one removes the open copies and keeps done or skipped ones
(`retire_template_item`). Items added or visibly changed carry
`pending_notice`; the daily `send_checklist_change_notices_task`
(`speakers/notices.py`) emails each affected presenter, assignee or team
once with the new and changed items, then clears the flags, so a quiet day
sends nothing.

### Reminders

`speakers/reminders.py` sends one digest per presenter (open speaker items
due within 7, 3 or 1 days, computed against today in the presenter's
timezone) and one per assignee, or to `SpeakerSettings.organizers_email`
(falling back to staff accounts) for unassigned organizer items, using the
edition's `conference_timezone`. `ReminderLog` is unique on
(item, threshold), so a reminder is never repeated. Daily Celery task
`send_checklist_digests_task`, seeded by migration 0004 (07:00 UTC for every edition: the "today" logic is per presenter timezone, the send time is not, so a presenter in Vancouver gets theirs late in their evening; per-timezone send times are a later refinement).

### Handbook

An edition can have several guides (`Handbook.key`: `speaker` by default,
plus `workshop`, `keynote`, `performer`, ...), each versioned
(`current(conference, key)`, `draft(conference, key)`) and normally just a
link to the conference site (`url`, default
https://conference.pyladies.com/docs/) with an optional note. A checklist
template line with the `handbook_read` rule names the guide it requires
(`requires_handbook`, blank = `speaker`), so a presenter on a keynote and a
workshop gets one item per guide. Organizers manage guides at
`/speakers/settings/handbook/`; presenters open each required guide from
`/speakers/me/guide/` and tick "I have read the ... guide", which records a
`HandbookReadReceipt` for that version, the way a terms-of-service
acknowledgement works. There is no automatic tracking. Publishing a new
version of one guide re-opens only the items that require it.

A new guide starts unpublished, pointed at the docs index above. That
placeholder is deliberate: it satisfies the editor's "a link or a note"
check, so an organizer may publish a guide that only says "see the docs"
and refine the address later. The guide list also names every key the
edition's checklists require but nobody has written yet, marked "not
created yet" with a button that opens the add form ready filled; without
it a "Read the workshop guide" item would sit open with nothing to read
and nothing on the organizer side to say so. On the speaker side,
`required_guide_keys` returns only what their own items name: a presenter
with no checklist yet is asked to read nothing.

### What everyone gets, and what their session gets

The every-presenter template holds the lines that are about the person
rather than a session: bio and headshot, registration, Discord and the tech
check. It applies to every presenter whatever their role, so an opening host
now carries those four as well, which is deliberate: a host registers,
joins Discord, appears on the schedule and goes live like anyone else.

The speaker guide is not in that list. A presenter reads one guide, the most
specific one their sessions call for: the workshop, keynote or performer
guide where there is one, and the general speaker guide otherwise, carried
by those templates as a once-per-presenter line. Two "read the guide" items
falling due on the same day read as a bug rather than as two guides.

Folding an edition that predates this (`manage.py dedupe_general_items`, and
loading the defaults) keeps one copy per presenter and prefers one they have
already done, because nobody should be asked to redo something they
finished. Every other copy goes, whatever its status: the template line is
deleted straight afterwards and `ChecklistItem.template_item` is SET_NULL,
so anything left behind would become a one-off item nothing can ever
collapse again.

### Checklist change notices

A template line that is added, edited or deleted reaches the checklists
already made from it at once; there is no back-fill step. Items added or
visibly changed (title, description, due date) are flagged on the row
itself, and a daily job emails each affected presenter, assignee or team
once, then clears the flags, so a quiet day sends nothing. A row can only
carry one flag: `flag_notice` lets NEW outrank CHANGED, because an item
someone has never seen is new to them whatever happened to it afterwards.
One failed mailbox is logged and counted, never raised, as in the reminder
digests.

### Agreeing to the Code of Conduct and the Terms of Service

Accepting an invitation creates the account and signs the presenter in, so
they never meet the signup form that collects the two agreements, and the
profile form cannot record them (its boxes are a disabled display of what
signup captured). The portal-wide gate,
`portal_account.agreements.AgreementRequiredMiddleware`, closes that: any
signed-in account without both agreements is redirected to a page that asks,
whatever route it arrived by.

A presenter gets the speaker welcome page instead of the plain one, because
it asks for a username and an optional password as well. That is wired
through `settings.ONBOARDING_URL_RESOLVERS`, which names
`speakers.onboarding.welcome_url_for`; `portal_account` knows nothing about
this app. The welcome page skips itself on `has_agreed`, the same question the gate
asks: when it asked a different one ("does a profile exist"), a presenter
whose profile predated the agreements bounced between the two forever.
Nothing on the speaker side routes onboarding any more, since the gate
runs before every view. Any page named by
a resolver is used once; if the next gated request arrives from somewhere
else and the agreements are still missing, the gate falls back to its own
page, which always collects them. A settled agreement is remembered in the
session, so the check costs nothing after the first page.

### Columns and the deploy window

The release migrates before it rolls out, so the previous release keeps
serving for a few seconds against the new schema. A column added to an
existing table therefore has to be writable without being named: nullable,
or carrying a `db_default` as well as its Python `default`. Without that
those inserts fail (production, 2026-09-22).

`tests/speakers/test_deploy_window.py` reads the migration graph, finds
every column added to a table that already existed, and checks each one, so
this holds for columns added later rather than for a list someone kept up
to date. A foreign key cannot have a default, and the test names that case
with its reason; the way to add one without a window is to add it nullable,
backfill it, then tighten it in a later release.

Removing a column is the same window in reverse: take it out of the model
and deploy, then drop it from the table in a follow-up migration, so no
running process selects a column that is already gone.

### The one dependency that points outward

Everything here depends on `portal`, never the reverse, with a single
exception: the conference edit form carries the speaker-portal switch,
which lives on `SpeakerSettings`. `portal/forms.py` reaches it through
`apps.get_model` behind an `apps.is_installed("speakers")` guard rather
than importing this app, so the core form still loads without the feature
module and there is no import cycle waiting to happen. If a second such
edge ever appears, give it a thin accessor module here rather than
repeating the registry lookup.

### Background jobs

Celery (`portal/celery.py`, broker from `CELERY_BROKER_URL` or `REDIS_URL`),
with django-celery-beat's database scheduler for periodic jobs
(`CELERY_BEAT_SCHEDULER`, edited in the admin under "Periodic tasks", seeded by
migrations such as `portal_account/migrations/0004_*`). Processes are in the
`Procfile` (`worker`, `worker-beat`). Enqueue through `common.tasks.enqueue`
(`common/tasks.py`), which logs instead of raising when the broker is down.
Tests run tasks eagerly (`CELERY_TASK_ALWAYS_EAGER` when pytest is loaded).

### Email

`common.send_emails.send_email` (`common/send_emails.py`) wraps
`common.markdown_emails.send_markdown_email`: one Markdown template under
`templates/emails/<app>/*.md` extending `emails/base_email.md`, rendered once,
sent as both text and bleach-sanitized HTML. Backend is SMTP when
`DJANGO_EMAIL_HOST` is set, console otherwise; subjects use
`settings.ACCOUNT_EMAIL_SUBJECT_PREFIX`. Guide: `docs/developer/markdown-emails.md`.

### Previewing an invitation

Both invite forms show the email the Send button would produce: recipient,
subject and the whole rendered body, wrapper included, from the same
`invitation_subject()` and `invitation_context()` the real send uses, so the
two cannot drift. `emails.render_invitation_preview()` sets `preview` in the
context, which the template uses for the only two differences: the personal
message is boxed and highlighted, and the accept address is shown as code
rather than as a link, since it is a placeholder until a token is minted.
The organizer-only `speakers:invitation_preview` endpoint renders it, and
htmx asks for it when a form becomes visible (`intersect once`) and again as
the note is typed, so a session page listing several unconfirmed presenters
builds no email until one is asked for.

### Next year

"Start next year" (`portal/views.py`, `StartNewYearView`) offers "Copy the
speaker portal setup" and "Enable the speaker portal". The copy is
`speakers.seeds.clone_speaker_setup`: checklist templates and items, the
latest published version of each guide as an unpublished draft, and the
settings except the pretix event, token and secret. The conference edit
form can flip the flag later.

### Absolute links in email

`speakers.emails.absolute_url()` builds links from the current
`django.contrib.sites` `Site` domain (`http://` under `DEBUG`, `https://`
otherwise). The domain is data: `manage.py set_site_domain <host>` or the
admin's **Sites** page, documented in `docs/developer/setup.md` and
`docs/developer/deployment.md`. A fresh database says `example.com`.

### Templates and front end

Repo-level `templates/<app>/`, Bootstrap 5 (`django_bootstrap5`), Font Awesome
kit, one stylesheet `portal/static/css/portal.css` (no inline `<style>`
blocks; djlint enforces template formatting). Two-column pages extend
`portal/base_sidebar.html` and fill `sidebar` with a rail partial
(`templates/portal/_organize_rail.html` for organizers,
`templates/volunteer/_volunteer_rail.html` for the personal hub), each item
via `portal/_sidebar_item.html`. There is no htmx or Alpine in the portal yet;
the design's inline interactions will bring htmx in when Stage 2.5 needs it.

### Markdown

`portal/templatetags/portal_extras.py` has a `markdownify` filter
(python-markdown + bleach) used for team descriptions. Speaker-facing markdown
(`*_md` fields) renders through `speakers.markdown.render_md()` (python-markdown
+ `nh3`) and the `speaker_md` filter in `speakers/templatetags/speakers_extras.py`.
The source is stored, never the HTML.

### Tests

pytest + pytest-django, `tests/<app>/`, shared fixtures in `conftest.py`
(`portal_user`, `admin_user`, autouse `conference`). No factory library is
installed; this app keeps small factory functions in `tests/speakers/factories.py`.
`make test` enforces 100% coverage and runs `--reuse-db --no-migrations`;
`make lint` runs isort, black, djlint (check and lint), flake8 and
`makemigrations --check`.

## Conventions for this app

- App: `speakers/`, URL prefix `/speakers/`, namespace `speakers:`.
- Feature flag: `speakers.SpeakerSettings.speaker_module_enabled`, one settings
  row per Conference (`related_name="speaker_settings"`), read through
  `speakers.models.speaker_module_enabled(conference)`. Views mix in
  `speakers.mixins.SpeakerModuleRequiredMixin`, which 404s while the active
  edition is off and sets `self.conference`. The row also hosts later
  per-edition settings (program visibility, pretix, media limits).
- Organizer predicate: `speakers.permissions.is_speaker_organizer`
  (superuser or staff, matching the rest of the portal). Liaisons are
  `Presenter.liaison` users; `SessionQuerySet.visible_to` and
  `PresenterQuerySet.visible_to` scope what they see, and the
  `SpeakerStaffRequiredMixin` / `SpeakerOrganizerRequiredMixin` mixins gate
  the organizer side. An organizer item can be handed to any approved
  volunteer (`people.organizer_side_candidates`), so a third predicate,
  `is_speaker_assignee`, admits whoever carries one: `can_work_queue` (the
  `SpeakerQueueRequiredMixin`) gates the queue and the per-item actions, and
  `ItemActionMixin` then lets an actor touch an item only if they organize,
  liaise its presenter, or are its assignee. Assignees never reassign
  (`ItemAssignView` stays organizer-only) and never open presenter or
  session pages; their queue rows name those without linking, and the
  "My speaker tasks" rail entry keys on the same flag. An item owned by a
  team counts for every approved member of it: `permissions.approved_teams`
  and `permissions.owned_by` are the single definition the queue, the
  predicate and the per-item check all use, because those three drifted
  apart twice.
- Speaker side: `/speakers/me/...`, gated by `PresenterRequiredMixin` (the
  user must own a `Presenter` row in the active edition, else 403). The
  dashboard is a summary (sessions with "x of y tasks done", open to-do
  count); the checklist has its own page (`my_checklist`, all-by-due-date
  or grouped by session, `?session=` for one), and each session has a
  read-only detail page with its checklist next to the edit form. The
  personal rail is `templates/speakers/_speaker_rail.html`; the navbar shows
  "Speaking" through the `is_speaker_presenter` context flag, and the portal
  index routes presenters who are not volunteering this year to their
  dashboard.
- Onboarding: a presenter whose account has no `PortalProfile` yet is sent
  to `/speakers/me/welcome/` (`PresenterRequiredMixin.requires_portal_profile`)
  before any speaker page: editable username, names, pronouns, CoC and ToS
  agreements, optional password. The portal index routes such presenters
  there instead of the volunteer profile form, whose username and agreement
  boxes are disabled because signup collects them. Accepting an invitation
  also sends `emails/speakers/accepted.md` (account, sign-in options,
  sessions, next steps). A presenter who accepted generally and is later
  added to a session gets `emails/speakers/added_to_session.md` (session,
  role, slot if any, link to the session page); one who has not accepted
  is told through the invitation itself. The dashboard nags about setting a password until
  one exists or `Presenter.password_reminder_dismissed` is set.
- Headshots go through the default storage (`ImageField`, same as
  `PortalProfile.profile_picture`), so they land on Spaces when
  `USE_SPACES=true` and on disk otherwise. Direct-to-Spaces presigned upload
  is reserved for the multi-gigabyte video pipeline (task 4.1); headshots
  are small enough to pass through the app.
- Invitations: `speakers/services.py` (send, resolve, accept, decline,
  cancel), `speakers/emails.py` (rendering, signed token, URL),
  `speakers/tasks.py` (Celery). The `invitation_accepted` signal in
  `speakers/signals.py` is where Stage 2 instantiates checklists.
- Sessions and presenters are addressed by slug in every portal URL
  (`/speakers/sessions/django-101/`, `/speakers/presenters/ada-lovelace/`,
  `/speakers/me/sessions/django-101/edit/`), never by number: the portal
  replaces a spreadsheet with gibberish links, and a speaker should not
  read an ordinal out of their address. Slugs are unique per edition by
  database constraint (`-2`, `-3` on collision), derived from the title or
  display name on first save, and never rotated by a rename. Organizers may
  edit a slug on the session and presenter forms (free text, normalised;
  reserved path words in `speakers/forms.py`; per-edition clash refused;
  blank keeps the current address). Scoped views resolve through
  `slug_field`/`slug_url_kwarg` on the session and presenter mixins, and
  lookups stay scoped to the active edition, so the same slug in another
  year does not resolve. Settings pages (types, roles, checklist templates)
  and item actions keep integer ids: they are not identities anyone shares.
- Edit windows. A speaker edits their session's title and web address,
  and their own display name and web address, only until an organizer
  schedules the session (`Session.identity_locked`,
  `Presenter.identity_locked`, from `IDENTITY_LOCKED_STATUSES`: scheduled,
  published, cancelled). The speaker forms take `locked=` and drop those
  fields, so a stale POST carrying them is ignored, and show them read-only
  via `form.locked_fields`. Content fields (summary, outline, bio, photo,
  links) stay editable until the session is published, as before, and
  everything is locked for the speaker after that. Organizers edit every
  field at every status; changing an identity field on a locked row logs
  `session.identity_changed` / `presenter.identity_changed` with old and
  new values and warns that shared links may break.
- Checklist item descriptions (`description_md`, Markdown) render under the
  title on the speaker's to-do list, the organizer's item rows and the
  template detail page; every seeded speaker-owned line has one.
- Checklist engine layering, lowest first: `lifecycle` (session status
  helpers, models only) < `checklists` (instances and status changes) <
  `rules` (auto-completion registry) < `receivers` (signals, registered in
  `apps.py`). A module imports only from layers below it.
- "Today" comes from `speakers.clock.today(tzinfo=None)` and nowhere else.
  Organizer pages, the board, the queue and `ChecklistItem.is_overdue` use
  the UTC date; the speaker dashboard passes the presenter's timezone so a
  due date is not overdue at breakfast in Lima because it is already
  tomorrow in Berlin. Anything that judges "overdue" on a presenter's
  behalf (reminder emails, task 2.8) must pass `presenter.tzinfo` too.
- Celery tasks are plain `@shared_task` unless they retry for real:
  `sync_order_task` and `pretix_reconcile_task` declare `autoretry_for=(PretixError,)`
  with back-off, because pretix being briefly unavailable is exactly the
  case a retry fixes. Otherwise no `bind=True` / `max_retries` unless the body calls
  `self.retry`; `bind=True` and `max_retries` on a task that never retries
  are noise.
- Checklist item status changes go through `speakers.checklists`
  (`set_item_status` and friends), never a bare save or the admin: that is
  where the activity log entry, the "no hand-ticking automatic items" rule
  and the session confirmation retry live. `ChecklistItemAdmin` shows
  status read-only for that reason.
- Pretix registration matches the manual `Presenter.pretix_order` link,
  then the order's buyer email case-insensitively, then attendee emails in
  the order's JSON positions, which are compared exactly against the
  lower-cased presenter email. An attendee email typed with capitals in
  pretix is missed; link the order by hand in that case.
- The two checklist unique constraints use `nulls_distinct=False`, which
  needs PostgreSQL 15 or newer (older servers drop the clause with a
  `models.W047` warning, and session-level items could then duplicate).
  `compose.yml` runs Postgres 16; see the deployment docs for production.
- One migration per pull request. While a branch is being built it may
  grow several steps, but before the PR branch is pushed they are squashed
  into a single regenerated file (delete them, `makemigrations speakers`,
  check with `makemigrations --check` and a `migrate` on a fresh database).
  A migration is frozen the moment it is **merged**: the cabotage release
  step runs `migrate` against production on every deploy of `main`, so a
  merged file is never edited, deleted or renumbered again, and later
  changes are always new files. Pull request deployments used to apply
  migrations from open branches too; they are disabled for exactly that
  reason (`0002_repair_invitation_sent_to` is the cost of learning it).
  See the deployment docs, "Release step and migrations".
- Every model: `conference` FK, admin registration, factory function,
  isolation test. Join and child rows (`SessionPresenter`, `ScheduleSlot`)
  carry a non-editable `conference` copied from their session on save.
- Status changes are model methods on `Session` (`mark_invited`, `confirm`,
  `schedule`, `publish`, `cancel`) that raise `speakers.models.TransitionError`
  when a precondition fails; views turn that into a message. Accepting an
  invitation is the presenter's confirmation: no seeded checklist item is
  required, so a content session becomes CONFIRMED as soon as every required
  presenter has accepted. Organizers can still mark a template line required
  to gate that.
- Enumerations live in `speakers/constants.py` as `TextChoices`, except
  session types and presenter roles, which are rows: `SessionType` (code,
  name, `is_content`, default duration and delivery, `spans_all_channels`,
  the allowed `roles` and a `default_role`) and `PresenterRole` (code, name,
  `email_word`), both per edition. `speakers/program_types.py` seeds the
  defaults (`seed_program_types`, also run when a `SpeakerSettings` row is
  saved and by `manage.py seed_program_types`) and never overwrites organizer
  edits. Code reads the flags, never a particular code; seeds, clones and
  tests look rows up by `code`. `SessionPresenter.clean()` refuses a role the
  session's type does not allow, and `Session.clean()` refuses a type change
  that would leave someone in a disallowed role. A type with no roles (a
  break) takes no presenters. Organizers edit both on the "Types and roles"
  settings page (`speakers:program_types`), whose `SessionTypeForm` is
  where "the default role must be one of the allowed roles" is enforced
  (the admin saves the many-to-many after `full_clean`, so the model cannot
  check it). Names are English only for now; per-language names arrive with
  the public schedule (design §11 and Stage 5).
