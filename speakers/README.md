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
  the organizer side.
- Speaker side: `/speakers/me/...`, gated by `PresenterRequiredMixin` (the
  user must own a `Presenter` row in the active edition, else 403). The
  personal rail is `templates/speakers/_speaker_rail.html`; the navbar shows
  "Speaking" through the `is_speaker_presenter` context flag, and the portal
  index routes presenters who are not volunteering this year to their
  dashboard.
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
- Celery tasks are plain `@shared_task` unless the body calls
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
  when a precondition fails; views turn that into a message.
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
  the public schedule (design §7.1 and Stage 5).
