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
(`PortalProfile.profile_picture`, `PyladiesChapter.logo`).

The speaker side of the media pipeline is a per-edition switch,
`SpeakerSettings.media_for_speakers` (off by default; "Media" fieldset on
the Speaker settings admin form; `models.media_for_speakers`). Off, a
speaker's session page has no Files tab, no video card and no upload
action, `media.can_upload` refuses a presenter and `media.can_download`
refuses them the shared files; organizers keep every page and can upload
a performer's raw video on their behalf, so the checklist lines that key
on files still complete. On, the performer uploads and sees what the team
shared.

Speaker media is different (design §8.8, task 5.1): performance videos are
gigabytes, so they never pass through the app. `speakers.media.MediaBucket`
talks to a **private** bucket named by `SPEAKER_MEDIA_BUCKET` (empty means
uploads are off and the endpoints answer 503), through the same `AWS_*`
credentials, its own endpoint and region (`SPEAKER_MEDIA_ENDPOINT_URL`,
`SPEAKER_MEDIA_REGION`, each falling back to the `AWS_*` pair when unset or
blank), with s3v4 signing. The deployment guide is the only guard against a
wrong endpoint: nothing checks it at release. The browser starts an upload
(`POST sessions/<slug>/uploads/`), gets presigned part URLs in batches of
`UPLOAD_PART_URL_BATCH`, PUTs the parts itself, and asks the portal to
complete or abort; `MediaUpload` is what the portal knows about an upload
in flight, and completing it makes the `MediaAsset` (next version for the
session, kind and language; the previous READY one becomes SUPERSEDED) and
sends `asset_ready`, on which the asset rules re-evaluate. Who may upload
what is `media.can_upload`: organizers any kind, a presenter on the session
their raw video, and only once the session is theirs (a proposal waiting
for an answer, or declined, has no channel into the bucket); every upload
endpoint asks it, so a presenter taken off a session loses an upload in
flight too. What the browser declares is checked twice: the declared size
against `SPEAKER_MEDIA_MAX_BYTES` when the upload starts, and the object's
real size against the declaration when it completes, since the parts are
PUT to the bucket out of the portal's sight; an object that disagrees is
deleted and the upload refused. The raw video is filed under no language
(`media.clean_language`), one line per session, so versions supersede each
other and the length rule reads one line; other kinds take a well-formed
tag. A video kind must look like a video, by type or extension
(`media.clean_content_type`). Downloads are presigned too
(`MediaAsset.download_url`), behind `media.can_download`: organizers and
the session's liaisons fetch anything, a presenter on an accepted session
their own raw video and whatever the team has marked `shared_with_speaker`
(`MediaShareView`, a button on the file row; design §8.6), while it is
the current version: a replaced version loses the flag and is withdrawn.
Sharing stamps `MediaAsset.shared_at`, and the daily checklist digest
(`reminders.py`) tells each presenter about the files newly shared with
them, once each (`SharedFileNotice`, `media.new_shared_files`; design
§13.2): a presenter with new files and nothing due still gets the email,
the subject names what is inside, and nothing goes out when there is
neither. "Once" is per presenter and file row: a file unshared and shared
again is the same file and is not announced twice, while a replaced
version is a new row and is. The migration that adds the table marks
everything already shared as told, so the first digest after a deploy
announces only what is shared from then on. The other direction is
immediate: a speaker's own completed upload (`media.uploading_presenter`:
not the team's, not a job's) queues `send_upload_notice_task` on commit
from `on_asset_ready`, and `emails.send_upload_notice_email` tells their
liaison, or the team's inbox without one, with the version it replaces and
a link to the Files section; reply-to is the speaker. With nobody to tell
(no liaison, no team address, no staff address) nothing is sent and the
gap is logged; the task is an `email_task` and checks the record first.
The speaker's session page lists the shared files (`media.team_files`)
and the earlier raw versions without the reviewer notes, which are the
team's (`show_notes` on the row partial). Promo materials are `PROMO` assets with a free `variant`
("square", "gif"); versions count per kind, language and variant, and the
seeded promo lines tick on the first file and the first share
(`AutoRule.ASSET_SHARED`). A file line (kind and language on the
session) has a title (`MediaAsset.title`, "Poster for the panel"): asked
once in the upload panel, prefilled there from `media.line_titles`,
inherited by later versions and variants in `complete_upload`
(`media.line_title`), and edited for the whole line at once
(`media.set_line_title`, `MediaTitleView`, which swaps the group
`_media_group.html` in place). Deleting a line takes every version of it
(`media.delete_line`, `MediaDeleteView`, design §8.8 "Deleting a file"):
organizers any line, a performer their own raw video while every version
is theirs (`media.can_delete`), after typing the shown file's name into
the page's one dialog (`_media_delete_modal.html`, `static/js/media-delete.js`);
the rows go in one transaction, with the finished `MediaUpload` rows that
pointed at them and any machine transcript made from a video on the line
(a reviewed one a person uploaded stays), and the `post_delete` receiver
drops each object, its thumbnail and an admin-attached file once the
transaction commits (`transaction.on_commit`, so a rollback never leaves a
row without its file), the same receiver the admin's session delete
cascades through (an open `MediaUpload` is aborted there too). A cancelled
session keeps its files. The text preview answers with
`X-Frame-Options: SAMEORIGIN`, since the clickjacking middleware's `DENY`
would leave the fold's iframe empty. Bulk download (task 5.6) is
`speakers/exports.py` and `speakers/export_views.py`: an organizer picks
a scope (kinds, language, sessions, latest or every version, newer than
a moment), `create_export` records a `MediaExport` (count, bytes, links
until), and the export's page offers the same set two ways: a zip the media
worker builds under `SPEAKER_MEDIA_ZIP_MAX_BYTES` (`build_export_zip_task`,
emailed through the recorded sender with the link withheld), first, and
`download.sh` with resumable curl and the manifest embedded (plus an
aria2 input file) as the advanced route. The scope form's session
picker (`static/js/media-export.js`) is an explicit "every session" or
"only these" choice over a filtered checkbox list grouped by type. Every path
lays files out as `pyladiescon-<year>/<slug>/<kind>/v<n>[-<lang>][-<variant>]-<name>`
with `manifest.csv`. Links live `SPEAKER_MEDIA_BULK_URL_TTL` (12 h);
Maintenance > File exports lists every export, and the nightly "Expire export
zips" task drops the zip of an export whose links have expired, so zips
bounded per export by `SPEAKER_MEDIA_ZIP_MAX_BYTES` do not add up for
good. The page opens with the raw videos chosen and always renders; an
export itself needs at least one kind. Every cell of every CSV the
app writes, the manifest included, goes through `spreadsheet.safe_cell`:
one line, never a formula, which is also what keeps the manifest embedded
in `download.sh` inside its heredoc. Machine transcription (task 5.7) is
`speakers/transcription.py`: with `SPEAKER_TRANSCRIBE_ENGINE=local` the
portal has an engine (`FasterWhisperEngine`, the one implementation of
the small `Engine` interface; `get_engine`), and an edition with
`SpeakerSettings.auto_transcribe` on gets a draft for every raw video
that lands (`should_transcribe`: READY, the switch, and no reviewed
transcript on the video's own line; `start_job` from `on_asset_ready`).
A draft is filed on a line of its own, named after the video (`video1.mpg`
gives `video1-en.vtt`) and keyed by `transcript_variant`: the file name stem
for a person to read plus the video asset's pk, which is what keeps it
unique (a name alone collides when two exports differ past the column's 40
characters, or when a raw video and a final cut share a name). Several
videos on a session each get a transcript, and only a re-run of the same
video makes a new version. A reviewer's corrected file supersedes the draft
only when it goes up under the draft's variant, so the panel's Variant field
lists the variants already on the session (`line_variants`) with a line of
help; a transcript uploaded with no variant is a session-wide file and bars
no video's draft, so one review never stops the others. Organizers
start or retry one from a video's row (`MediaTranscribeView`). A
`TranscriptionJob` row carries the state the row shows; the task
(`transcribe_asset_task`, media queue, `acks_late`) extracts the audio
with ffmpeg from the presigned link into a temp file of raw 16 kHz
samples (so the engine never decodes a container itself), hands it to
the engine, writes WebVTT, puts it in the bucket and records it through
`media.record_asset` with `generated_by` set, which the rows show as
"machine draft"; the "Transcribe" item ticks, "Review transcript" stays
open, and a person's next version supersedes the draft. Failures land on
the job row and in the activity log; a job still queued after
`SPEAKER_TRANSCRIBE_STALE_HOURS` is failed by the nightly "Fail stale
transcription jobs" task, which is how a missing media worker shows on
the page. The library is in `requirements-media.txt` and the model in
`/opt/whisper`, both baked into any image built with a non-empty
`WHISPER_MODEL`, which the Dockerfile defaults to `small` so cabotage, which
passes no build arguments, still gets an engine. `compose.yml` holds it empty
for the dev images, which is what keeps local builds and CI free of the
library and model; a plain `docker build` or the platform's build carries them,
in the web and beat processes too, since one image serves every process (a
separate media-worker target would avoid that, and is the alternative if the
size matters). Tests never import the library (`_load_model` is patched). Thumbnails (task 5.8) are
`speakers/thumbnails.py`: `on_asset_ready` queues `make_thumbnail_task`
on the `media` queue for images and videos, Pillow scales an image and
ffmpeg takes a frame of a video (three seconds in, the first frame for a
shorter clip) into `<storage_key>.thumb.jpg`, recorded in
`MediaAsset.thumbnail_key` or explained in `thumbnail_error`;
`MediaThumbnailView` redirects to an inline link, `_media_thumb.html`
shows it or an icon, and `with_video_status` annotates the sessions list
with the raw video's. Tests stub `thumbnails.run_ffmpeg` beside the
ffprobe stub in `tests/speakers/conftest.py`. A few bitmap types, video,
audio and small text files such as transcripts (`MediaAsset.preview_kind`,
an allowlist of concrete types from the content type or the name; SVG,
which carries script, only downloads; text goes through `media.read_text`
as plain text rather than a signed link) get a closed "Preview" fold on
their rows (`_media_preview.html`) that loads the file through
`MediaPreviewView`, an inline presigned link that lives a minute like a
download's; nothing is fetched until the fold is opened, and video streams
by range requests, each one through the endpoint for a fresh link. A video
kind is stored with a `video/` type whatever the browser declared
(`media.clean_content_type`), since the stored type is what the file is
served back as.
Uploads nobody finishes expire after
`SPEAKER_MEDIA_UPLOAD_TTL_HOURS` (the "Expire abandoned uploads" task
nightly, `manage.py expire_abandoned_uploads` by hand); the bucket needs its
own lifecycle rule as the backstop (`AbortIncompleteMultipartUpload` after
7 days, see the deployment doc). Tests run against moto's S3.

What reclaims space: nothing in the portal deletes an object on its own.
Deleting a `MediaAsset` row (the admin) drops its object too
(`receivers.drop_the_object`), and a `MediaUpload` row that fails to insert
aborts its multipart at once. Superseded versions keep their objects for
as long as their rows last, because the pages show them as history; an
edition's files are reclaimed by deleting the rows, or by a bucket rule
on the edition's prefix once the videos are published.

The duration probe (task 5.3) is `speakers/probe.py`: `on_asset_ready`
queues `probe_asset_task` for the video kinds (`constants.VIDEO_KINDS`)
once the row is committed, routed to the `media` queue and the
`worker-media` process (`CELERY_TASK_ROUTES`, `Procfile`); the compose
worker consumes both queues. `ffprobe` reads the object's headers over a
presigned link and the answer lands in `MediaAsset.duration_seconds`,
whose save re-runs `VIDEO_LENGTH_OK`. A probe that cannot answer (no
`ffprobe`, unreadable file, no bucket) writes the reason to
`MediaAsset.probe_error`, logs an error and leaves the asset READY; the
file rows and the performer's card show it. The task tries three times, a
few minutes apart, before a failure stands; `manage.py probe_media`
re-queues the videos still without a duration (`--all` for every video,
`--asset` for one). Tests stub `probe.run_ffprobe`
through an autouse fixture in `tests/speakers/conftest.py`, and one test
runs the real binary on a two-second fixture when it is installed.

Nothing about uploads or video appears on either session page until
`SPEAKER_MEDIA_BUCKET` is set (`media_on` in both views): without storage
the panel could only fail, so a portal deployed ahead of its bucket shows
no upload panel, no "Add file" and no video card, and the team gathers
recordings as before. The organizer page's video card is also gated on
`can_download_media` (`media.can_download`), like the blocks around it,
so it holds if the page's own gate ever widens.

The browser side (task 5.2) is `static/js/media-upload.js` driving
`templates/speakers/_upload_panel.html`: it slices the file, PUTs three
parts at a time with retries and backoff, and remembers the upload id in
`localStorage` (per session, kind and user) so that coming back after a
closed tab and choosing the same file again resumes: the detail endpoint
says which parts the bucket holds (with their ETags), and only the rest go
up. Choosing a different file aborts the remembered upload first. The
performer's session page shows the card (`media.video_panel`: current raw
video, its duration against `media.video_limit_minutes`, earlier versions,
open uploads of theirs); the organizer's session page has a Files section
(`media.asset_groups`, one block per kind and language, the newest READY
version first) with a reviewer note per asset (`MediaNotesView`) and a
panel for any kind. Downloads go through `MediaDownloadView`, which mints
the presigned link on the click for whoever `media.can_download` admits
(above). The link lives a minute (`media.DOWNLOAD_LINK_TTL`): the browser
follows it at once, and what the address bar and any proxy log keep has
expired by the time anyone reads it. The JavaScript has no unit tests and
no linter runs on it; the server is the authority on size and type and
the panel shows its answer, and the 200 MB resume check is done by hand
against a bucket (setup doc).

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

### Proposals

An edition can open the door: while `SpeakerSettings.proposals_open` is on,
anyone with a portal account proposes a session at `/speakers/propose/`,
speakers already on the program included. Only session types with
`open_for_proposals` are offered, so nobody proposes a coffee break. The
switch and the intro text live in the settings row's admin form, under
"Proposals"; the field defaults to off and nothing else in the portal turns
it on, so an edition whose landing page shows no "Propose a session" button
has not opened it there yet. "Taking proposals" is defined once,
`services.proposals_open` (module on and switch on); the landing page, the
hubs, the Organize rail and the propose view all read it.

The settings admin pins its fieldsets, and a pinned fieldset drops a field
added later without a word: the proposals switch shipped unreachable that
way. `tests/speakers/test_admin.py` now checks every speakers admin that
pins fields against the model, so a new field must be offered, read-only,
or named in `exclude` with a reason. `pretix_create_vouchers` is the one
exclusion: voucher creation is not built, and `pretix.create_voucher`
raises while the switch is on.

A proposal is real rows from the start: a `Presenter` with the account
linked, a `Session` in `PROPOSED`, an unconfirmed `SessionPresenter`, and a
`Proposal` carrying the review. The notice goes to
`SpeakerSettings.organizers_email` (`emails.organizer_inbox`, which the
reminder digest and the co-presenter suggestion use too, falling back to
the staff accounts while the field is blank, and adding the presenter's
liaison where there is one): a proposal is work for whoever runs the program, and
`is_staff` is neither per edition nor a job description. Approving runs the acceptance path an
invitation takes (`services.approve_proposal`), so the checklists and the
confirmation are the ones a speaker always gets, dated from the approval. The
email is not the same: an approval sends `proposal_approved.md` ("Your session
is in"), while accepting an invitation sends `accepted.md` ("Welcome aboard"),
so an approved proposer never gets the welcome email. Rejecting keeps the rows and locks the session's identity, and an
organizer can still approve it afterwards: slots open up when something is
cancelled, and the whole acceptance path runs then, dated from the second
answer.
Withdrawing, while nobody has answered, keeps both rows and takes them off
the organizers' list: withdrawing usually means "not like this" rather than
"forget it", so the writing stays, the proposer can keep editing it, and
"Send it again" puts it back in the queue as a fresh pending proposal.

A speaker already on the program sends a proposal too: one door, whoever is
knocking. They are spared the "About you" half, which they filled in at
onboarding, and the organizers keep deciding what is on the program. An
earlier build let them add a session outright, which left two ways in that
said different things on the same pages.

Proposals are capped per presenter per edition (`MAX_PENDING_PROPOSALS`),
and `Session.created_by_presenter` marks what came in this way.

`Presenter.is_onboarded` is what the speaker area gates on, rather than the
presenter row existing: a proposer has a row before anyone has said yes.
On the program means a confirmed link to a session of the edition, or an
accepted invitation to the conference in general: a general invitation
carries no session, so accepting it confirms nothing, and the acceptance
itself is the yes (sessions added later are confirmed from it). The rule
is written once, `PresenterQuerySet.onboarded()`, and read by everything
that decides where a presenter may go: the `PresenterRequiredMixin` gate,
the portal index and the speaker index redirects, the `is_speaker_presenter`
navbar flag, the agreements-gate resolver, and `Presenter.is_onboarded`
itself. When #436 tightened the rule from "a presenter row exists" to
"on the program", the gate and the navbar flag moved with it (the flag as
an inline copy) and the two redirects did not, so a speaker with an
accepted general invitation was refused by the gate and sent back to it by
the redirects. Two lessons, one remedy: tightening a rule means finding
everyone who decides the same thing, and a reader that restates the rule
can drift from it, so a new reader calls the queryset. The checklist board uses
the looser `not_only_proposing()`: a presenter an organizer created, invited
or not, is still their work, while someone whose every session is still a
proposal or a refused one is not a row until an answer puts them on one.

The board's third tab (`board.build_post_production_board`, design §4.2)
has pre-recorded sessions down the side and the session-scope pipeline
items across, with the newest READY raw and processed video per row,
blocked rows first with the note (the overage), then the most overdue.
Three queries whatever the size. A cell shows the status and who is on
it and links to the item page, where it is assigned: a select per cell
would put the whole assignee list on the page a few hundred times. The
sessions list's Videos column reads the same facts from
`SessionQuerySet.with_video_status` (three subquery annotations, so the
list stays flat).

Title and display name are collapsed to one line on the way in
(`forms.one_line`): both reach email subject lines, and a newline in a
header makes Django refuse the message, which would silently cost the
proposer every email about their proposal. Both are escaped again on the
way into the organizers' email (`emails.as_written`), for the reason the
co-presenter note is fenced: a proposer's words reach organizers as words,
never as a link or an image.

**Liaison scoping is deliberately absent here.** Everywhere else a liaison
sees only their own presenters; the proposal queue shows them the whole
edition's. Someone proposing for the first time has no liaison, so scoping
by one would leave a liaison staring at an empty queue while proposals
waited. Deciding stays organizer-only (`can_decide`), so what a liaison has
is a reading of the program's inbox.

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
  `session_scheduled`, `guide_published`, `registration_open`,
  `final_cut_ready` (a READY processed video is on the session, which is
  what holds the performer's "Approve the final cut" until there is
  something to approve; re-read whenever an asset lands, changes or
  goes). Adding one is a code change, because the predicate is code.
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

Reply-To: `deliver_markdown_email` sets it to `DEFAULT_FROM_EMAIL` unless the
caller passes `reply_to=`, and never adds a recipient (the invitation link is a
sign-in credential, so nobody is copied). The speaker-facing emails (the
invitation, the acceptance, added to a session, the three proposal replies, and
the speaker side of the checklist digest and change notice) pass
`emails.team_reply_to(conference)`: `SpeakerSettings.organizers_email`, or
nothing when blank, so a reply goes to `DEFAULT_FROM_EMAIL` and not to a staff
account (`organizer_inbox` falls back to staff; replies must not). Point it at
the shared team address, never a person. Organizer-facing mail (the
organizers' copy of a proposal, the co-presenter suggestion, the organizer side
of the digests) keeps the `DEFAULT_FROM_EMAIL` default. Account email
(allauth) has no Reply-To.

Every send through `send_email` leaves a `common.SentEmail` row (design
§13.1, task 2.23): the addresses as sent, the subject, the template (which
is the kind), the rendered Markdown body, the ids of what it was about, and
whether it failed, with the error and no body. Whose it is comes from the
send context only where the address proves it (`common.send_emails.describe`):
a `presenter` or `user` in the context is the recipient when the email went
to exactly their address, so the organizers' copy of a proposal names the
proposer in its digest without ever showing in the proposer's own trail.
Failing both, an address that allauth has verified as exactly one active
account's is that account's (`_verified_owner`): an assignee's digest
carries items in its context, not the assignee. Callers pass `user`,
`presenter`, `session` and `conference` explicitly when they know more than
the context says (the change notices and the organizer digests pass the
assignee), and name in `secrets` any string that
must not be stored: the invitation's accept link signs its reader in as the
presenter (`InvitationView.post` logs the current user out and the
presenter in), so `send_invitation_email` withholds it and the record shows
`common.send_emails.WITHHELD` in its place. The same link is also withheld
by shape: `speakers.apps` registers its URL pattern with
`common.send_emails.register_credential_pattern`, and every stored body is
scrubbed against the registered shapes whatever the sender passed, because
on the first day a Celery worker still running the previous code recorded a
live link. A trail read by maintainers must never hold a credential; that
is the same reason account emails are not recorded at all. Two readers:
Maintenance > Emails
(`portal_account.views.MaintenanceEmailsView`, maintainers only, filtered
by edition, presenter, kind and outcome, searched by subject or address)
and "Emails we sent you" under Manage account (`MyEmailsView`, scoped by
`SentEmailQuerySet.owned_by`: the record's account, or the presenter row
linked to it, never the address alone). Account emails go through the
allauth adapter and are not recorded. Records are kept for the edition plus
`EMAIL_RECORD_RETENTION_DAYS` (365) and pruned nightly by the "Prune email
records" periodic task (`manage.py prune_email_records` by hand). Two limits
to know: a send that raises inside a caller's `transaction.atomic()` (the
checklist change notices) rolls its FAILED record back with everything
else, so that failure is in the log and not in the trail; and a process
that dies between the backend accepting the message and the row being
saved leaves a delivered email with no record. The trail reads ownership
from the live links (`user`, `presenter.user`), so re-pointing a presenter
row at another account moves its stored bodies with it; `link_presenter_user`
only ever links a verified address to a row with no account, so that takes
a staff edit, and is worth knowing before making one. The Maintenance page
shows a failed send's backend error; the personal page says only that it
failed. Bodies render through the email's own bleach allowlist with image
sources dropped (`SentEmail.body_html`), so reading a trail never fetches
from a third party. The sponsorship contract request to the PSF goes
through `send_email` too, so account emails are the only exception.

**Invitations marked sent with no email record.** `Invitation.sent_at` is
stamped by the web process when the email is queued; the `SentEmail` row is
written later, by the worker. A task lost between the two (a worker killed or
restarted while holding it, a broker outage) leaves the presenter page saying
"Sent" with nothing sent and no error anywhere. Maintenance > Invitations
(`speakers.delivery_views`, maintainers only) lists the active edition's
invitations that were expected to have gone out and have no successful record
(`speakers.delivery.unrecorded_invitations`: records are matched on the
template, `context_digest.invitation` and a time at or after the stamp, with
a minute for clock skew), shows a failed record's error, and sends one again
per button press (`retrigger`, through `send_invitation`, so a fresh link; no
bulk send, on purpose). The invitation's row is locked while it is sent, so
two presses cannot both send. It does not judge invitations from before
`records_began()`, which is when migration `common.0001_sent_email` was
applied and not the oldest surviving record (the prune moves that forward, and
a worker that was down at first leaves no early row), or ones that were opened
or answered. A row sent in the last five minutes is shown with a disabled
button. Every retrigger is an `invitation.retriggered` activity entry and
a log line. The design for tracking delivery properly is
`docs/architecture/email-delivery.md`.

**When an email task is interrupted.** The one-recipient email tasks
(`send_invitation_email_task`, the acceptance, added-to-session and proposal
approved and rejected tasks) use `common.tasks.email_task`: acknowledged late
and given back if the worker dies, retried when the mail server is down or
slow (not when it refuses the address or the login), with a time limit. A task
that runs twice checks first whether the send is already on record
(`emails.invitation_email_recorded` for the invitation), so the presenter is
not mailed twice. The proposal receipt, the co-presenter suggestion and the
digests send to several people and are not retried. `EMAIL_TIMEOUT` bounds the
SMTP connection. Settings and variables are in `docs/developer/deployment.md`.

**Logging.** `LOGGING` in settings sends the apps' INFO messages to stdout
(`PORTAL_LOG_LEVEL` to change it); without it the web process logged only
gunicorn's request lines. `enqueue` logs the id of a queued task, and
`send_invitation_email_task` logs its start, end and failure with the same
id, which is what the worker's own `received` and `succeeded` lines carry.
Each Procfile process is a separate deployment in cabotage with its own logs,
so the worker's lines are under `worker`, not `web`.

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

`templates/403.html` and `templates/404.html` extend `portal/base.html`, so a
refusal or a wrong address still has the navbar, sign-out and a way home.
There is deliberately no `500.html`: Django renders it with a bare
`Context`, no request and no context processors, so a page extending the
base would render a hollow navbar with no user and no conference, and any
later change to the base that queries would run during the outage that is
often the cause. Django's built-in 500 page needs nothing, and stays.

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
  user must be on the program in the active edition, `onboarded()` above,
  else 403). The
  dashboard is a summary (sessions with "x of y tasks done", open to-do
  count); the checklist has its own page (`my_checklist`, all-by-due-date
  or grouped by session, `?session=` for one), and each session has a
  read-only detail page with its checklist next to the edit form. The
  personal rail is `templates/speakers/_speaker_rail.html`; the navbar shows
  "Speaking" through the `is_speaker_presenter` context flag, and the portal
  index routes presenters on the program who are not volunteering this year
  to their dashboard; one not on the program goes to the volunteer hub, and
  the speaker index shows them a short explanation, so nobody is sent to a
  page that refuses them.
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
  isolation test. (`Proposal`, `ReadinessGate` and `HandbookReadReceipt`
  were registered late, in the proposals PR; the changelist smoke test
  covers every model, which is what caught them.) Join and child rows (`SessionPresenter`, `ScheduleSlot`,
  `Proposal`) carry a non-editable `conference` copied from their session
  on save.
- The schedule's places are `Room` rows (renamed from `DiscordChannel`,
  migration `0017_rooms`): deliberately generic, because only the name
  was Discord-specific. `url` and `discord_id` record which Discord
  channel a room is when the edition is online; nothing else cares.
- The schedule editor (design §10) is `speakers/schedule.py` (the grid's
  layout, day tabs, bulk double-booking warnings and timezone options,
  all in flat queries) and `speakers/schedule_views.py`: one page
  (`schedule/`, organizer-only, `?board=1` returns the grid-plus-sidebar partial for
  refresh) and ONE mutation endpoint, `sessions/<slug>/slot/`, where
  PATCH upserts the slot (a drag sends room and start, a resize sends
  duration, the keyboard form everything; a move without an end keeps
  the length) and DELETE removes it. Placing a CONFIRMED session calls
  `Session.schedule()`; removing a SCHEDULED one calls `unschedule()`
  (back to CONFIRMED, which reopens the identity fields); a PUBLISHED
  session keeps its slot. Everything is UTC end to end: the browser only
  relabels `data-utc` elements (`static/js/schedule-editor.js`), so the
  timezone switcher never touches what is stored or sent.
- The grid shows a trimmed day (design §10.2): `schedule._window` renders
  the program plus an hour each side, always on whole hours, and
  `ScheduleSlot.clean()` stores whole minutes, because every row time is
  derived from the window's start and a stray second would shift the
  grid. A drag can only reach an hour past the current window; the
  window grows after each change, so stretching further takes a few
  drags, or "Show the whole day".
- The presenter's schedule page (design §2.4) is `schedule.presenter_schedule`:
  public sessions plus the viewer's own in any on-schedule status, grouped
  by the presenter's LOCAL day with times pre-formatted in Python, because
  Django's date filter converts aware datetimes back to the current (UTC)
  timezone in templates. Nobody else's unpublished sessions appear; the
  viewer's own carry a "not yet public" badge. Calendar links are disabled
  placeholders until the feeds (task 4.4).
- The public program (design §11.5, task 6.1) is `speakers/public.py`:
  every public surface reads `public_program(conference, preview=None)`
  and `public_presenters(...)`, so the three switches live in one place.
  The edition's master switch is `SpeakerSettings.program_visibility`
  (INTERNAL by default: the public program is empty). A content session
  is public once it is on the published schedule AND an organizer ticked
  it (`Session.publish()`, undone by `unpublish()`, back to SCHEDULED);
  a program item (break, opening) goes public with the schedule itself,
  by the user's decision. A presenter is public only through a confirmed
  link to such a session and only if they have not opted out; anyone
  else is absent, never a "TBA". The organizers' Publishing page
  (`schedule/publishing/`, `publishing_views.py`) holds the switch, the
  ticks (disabled until a session is on the published schedule) and the
  website's preview link: a token signed with SECRET_KEY naming
  `SpeakerSettings.preview_key` (minted when the settings row is created,
  so showing the token never writes), with NO expiry by the user's decision;
  "make a new link" changes the key and revokes every older one, and
  every link stops working once the program goes public. The preview
  shows every session on the published schedule, published or not, but
  still honours a presenter's opt-out; preview responses are `no-store`. "Preview as public" (the
  editor's button, and the Publishing page) opens `schedule/preview/`:
  the website's own widget inside the portal, for organizers. While the
  program is internal it defaults to the draft (everything on the
  confirmed schedule, ticked or not, through the preview token) with a
  "Public now" switch; once public, only the public view.
- The public JSON API (design §11.1, task 6.2) is `speakers/api.py`
  (payloads and cache) and `api_views.py`, mounted at `/api/v1/` by
  `portal/urls.py`: `<conference>/sessions/`, `sessions/<slug>/`,
  `presenters/`, `presenters/<slug>/`, `schedule/` (slots grouped by the conference
  timezone's day, plus the rooms), and the calendar aliases
  `schedule.ics` and `sessions/<slug>.ics`. `<conference>` is the
  edition's slug, not the active edition, and an edition without the
  module is 404. Plain views, no DRF. Everything starts from
  `speakers.public`, so the visibility rules hold; every payload says
  which `program` state it shows (`published`, `internal`, `preview`).
  Markdown comes as the stored `*_md` and sanitized `*_html`: `*_md` is
  the raw source as typed, so a website must render only `*_html`;
  emails and `notes_md` never appear (a test walks every key). Absolute
  URLs in a payload (the `.ics` links, headshots) come from the
  configured Site through `emails.absolute_url`, never from the caller's
  host, since a payload is cached and served to everyone. A presenter who opted
  out is on their sessions by name with `slug: null`. Live responses are
  cached five minutes per edition under a generation key that
  `receivers.public_api_changed` bumps after commit on any save or delete
  of a session, presenter, link, published slot, room, session type,
  role or the settings; a response for a VALID `?preview=` token is built
  fresh with `Cache-Control: no-store`, and a junk token is served from
  the cache like any other request, so nobody can force a rebuild per hit
  or blank a CDN by appending a parameter. CORS: each edition's `AllowedOrigin` rows
  (one website per row, edited as a list in the speaker-settings admin;
  stored as browsers send an origin, lower-case scheme and host with no
  path, and refused with a path) are read through
  `SpeakerSettings.api_origins` and echoed back to a listed `Origin`,
  with `Vary: Origin`; a preflight (`OPTIONS`) answers a listed origin
  with GET/HEAD and the conditional headers (`If-None-Match`,
  `If-Modified-Since`), so the site may revalidate its cache. The list is not in the cache
  invalidation set: the header is computed per request. The Publishing
  page lists the allowed websites; someone who may change speaker
  settings in the admin (superusers, or staff granted the permission)
  gets an "Edit in admin" link, everyone else a note to ask an admin. No
  public per-presenter `.ics` yet.
- The website widget (design §11.2, task 6.3) is written readable in
  `frontend/widget/v1.js` and served minified from
  `portal/static/widget/v1.js`, built by `npm run build:widget` (terser,
  the repo's only Node dependency; the portal itself needs no Node). The
  build stamps the source's sha256 in the served file's header, and
  `tests/speakers/test_widget.py` fails when the source changed without a
  rebuild, or when the served file passes 15 KB; CI needs no Node. The
  site pastes the snippet the Publishing page shows:
  `<div data-pyladiescon-widget="schedule" data-conference="<slug>">`
  plus the script tag (it offers one per whole-program view, and copyable
  links to the JSON and `.ics` endpoints under "Data feeds"). Views:
  `schedule`, `sessions` (every content session as a card, in program
  order), `speakers`, `session` with
  `data-session="<slug>"`, and `speaker` with `data-speaker="<slug>"` (one
  profile inline, for a site that wants a page per speaker).
  The schedule: day tabs; times in the visitor's timezone (remembered in
  localStorage, as is the room picker, which appears once there is more
  than one room); on a container wider than 40rem a grid with a time
  column and one column per room in a stable order, rows of five
  minutes, so staggered sessions line up and program items (bands) span
  every room; narrower, a CSS container query turns it into one
  time-ordered list. Cards show the speakers' photos and names. A
  session title opens an overlay (a native `<dialog>`: Escape, focus and
  the backdrop come from the browser) with the full description; a
  speaker's name or photo opens theirs (`presenters/<slug>/`) with bio,
  links and sessions. Calendar links are subscribe-only (webcal, Google,
  Outlook.com). There is no starring: the user removed it.
  `data-api` points it at another portal (default: the script's own
  origin); `data-preview`, or `?preview=` on the host page, passes the
  preview token through. While the program is internal every view shows
  "Program coming soon" and every endpoint answers 200, so the browser
  logs nothing; if the API cannot be reached it shows a link to
  `data-fallback-url` (default: the portal's `/embed/<slug>/schedule/`,
  task 6.4). Styling: the `.plc` root and `--plc-*` CSS variables
  (`--plc-accent`, `--plc-muted`, `--plc-border`, `--plc-band`,
  `--plc-card`, `--plc-radius`, `--plc-modal-bg`, `--plc-modal-text`);
  text inherits the host page's font. Caching: `/static/widget/v1.js` is
  the stable address (WhiteNoise sends it with a short max-age, so the
  site always gets the current widget); the hashed copy WhiteNoise also
  serves (`widget/v1.<hash>.js`, listed in `staticroot/staticfiles.json`)
  is cached for a year and suits a CDN that should pin one version; bump
  to `v2.js` for breaking changes. A visitor's browser keeps an API
  response up to five minutes, so a change can take that long to reach
  an open page. Checked by hand in Chrome only (bare pages on another
  origin, 360 px, coming-soon, preview, error, multi-room and staggered
  demos); Firefox and Safari not yet.
- The calendar feeds (design §11.3) are `speakers/feeds.py` (a hand-
  rolled ICS writer, like the VTT one: escaping with every line ending
  normalised to one escaped newline, 75-octet folding counting the
  continuation space, CRLF) and `feed_views.py`: `schedule.ics` (the public
  program, `?sessions=`, `?kind=`, `?room=` filters; a non-numeric room
  answers 400), a per-session public feed, and a presenter's personal
  feed behind a signed non-expiring token (sessions they have ACCEPTED,
  public or not, cancelled ones carried with STATUS:CANCELLED until the
  next publish removes the row; `?sessions=` narrows it to one session
  for the speaker page's per-session link). Every link subscribes; there
  are no static downloads, because a downloaded copy is stale the moment
  a publish moves anything. UIDs are stable per session and edition;
  SEQUENCE is `PublishedSlot.ics_sequence`, bumped only by a publish;
  responses carry Cache-Control max-age=300, `private` on the personal
  feed. The feeds always serve the ACTIVE edition: once the next one is
  activated, an old personal-feed link answers 404 and the public feed
  switches to the new edition's sessions (per-edition URLs are planned
  in §11.3).
- The published schedule (design §10.1) splits the grid from what
  speakers see: `ScheduleSlot` is the organizers' draft, `PublishedSlot`
  the snapshot everything speaker-facing reads (their schedule page and
  session pages, `presenter_email_context`, both SESSION_SCHEDULED rules,
  later the feeds and the public program). Only sessions from CONFIRMED
  on publish (`schedule.PUBLISHABLE_STATUSES`): a DRAFT or INVITED
  session on the grid is the organizers' pencil, stays out of every
  publish, and nobody is emailed about a session they have not accepted;
  once it is confirmed, the next publish picks it up as a placement. The
  editor marks such a card "pencilled in" (dotted), never as unpublished
  (dashed), so cards and the publish counter agree. The
  update email likewise goes only to presenters with a confirmed link,
  and it words each line from the snapshot as it stands when the task
  runs, so a session a later publish restored is not announced as taken
  off, and a cancelled session is worded as cancelled (cancelling sends
  nothing itself, so this is how its speakers hear). `schedule.publish_schedule`
  diffs the grid against the snapshot and applies it in one transaction:
  this is when CONFIRMED becomes SCHEDULED (so `Session.schedule()` and
  `publish()` now require a PUBLISHED slot), when identity locks, when
  `ics_sequence` bumps on moves, and when removals return a session to
  CONFIRMED. The editor's grid mutations log `slot.placed`/`slot.moved`/
  `slot.removed` (drafting); the session-level `session.scheduled`/
  `session.rescheduled`/`session.unscheduled` entries are written by the
  publish (the editor's **Confirm schedule** button: it shares the
  schedule with speakers and makes nothing public; "publish" in the UI
  means the public program only). "Email the affected speakers" (default on) sends one recorded
  mail per affected presenter via `send_schedule_update_task`; the
  presenter row rides in the email context because the resend guard keys
  on the record's context digest. Organizer pages (sessions list, session
  detail) deliberately keep showing the working grid.
- The schedule grid's overlap rules live on `ScheduleSlot` (design §8.5):
  `clean()` runs on every save and refuses a slot sharing a room with
  another, or crossing an every-room band, except that two program-kind
  bands (`is_content` off on both types) may coexist. A cancelled session's
  slot stays as a record but frees its time (`OFF_SCHEDULE_STATUSES`). A
  presenter booked twice at once is deliberately NOT an error, because a
  moderator moving between rooms is legitimate; `presenter_clashes()` hands
  the editor the links to warn about. A session in `UNACCEPTED_STATUSES`
  cannot hold a slot at all, which is what lets the rules look through
  those statuses on the other side (an approved proposal would otherwise
  carry a quietly conflicting slot onto the grid). The checks are
  application-level; design §8.5 names the Postgres exclusion constraint
  that would make them a database guarantee.
- Status changes are model methods on `Session` (`mark_invited`, `confirm`,
  `schedule`, `publish`, `cancel`) that raise `speakers.models.TransitionError`
  when a precondition fails; views turn that into a message. Accepting an
  invitation is the presenter's confirmation: no seeded checklist item is
  required, so a content session becomes CONFIRMED as soon as every required
  presenter has accepted. Organizers can still mark a template line required
  to gate that.
- Enumerations live in `speakers/constants.py` as `TextChoices`, except
  session types and presenter roles, which are rows: `SessionType` (code,
  name, `is_content`, default duration and delivery, `spans_all_rooms`,
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
