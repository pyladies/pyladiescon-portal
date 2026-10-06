# Speaker Portal

The design of the speaker module (the `speakers` app): how presenters are
invited, what they and the organizers see, the two-sided checklists, the
media pipeline, scheduling, and the public embeds. Written as a proposal on
15 September 2026 for PyLadiesCon 2026 (first weekend of December, online on
Discord) and kept here as the reference for the module as it is built.

Where the built module answers a question differently from the proposal,
this page says what was built: the session types and presenter roles that
became rows (§8.1), readiness (§9.3a), and where a person's own tasks live
(§9.6). Smaller divergences, and the reasons for them, are listed in
`speakers/README.md`, which is the place to look when this page and the code
disagree.

**Stack:** Django, PostgreSQL, Digital Ocean Spaces.

---

## 1. Overview

PyLadiesCon 2026 is a special edition built around workshops, panels, and PyJam performances, with speakers invited directly by the organizing team rather than selected through a call for proposals. The speaker portal is the single place where that program is assembled and run:

- Organizers add sessions and the people presenting them, and send invitations.
- Speakers accept, fill in their bio and session details, and see exactly what they need to do and by when.
- Organizers see exactly what *they* owe each speaker — emails, promo materials, scheduling — and speakers can see that too.
- The schedule is built in the portal, placed in rooms (Discord channels, for an online edition), and shown to everyone in their own timezone.
- The conference website shows the schedule and speakers by embedding a widget from the portal, so there is one source of truth.
- PyJam performers upload their videos to the portal and the team tracks each video through post-production to YouTube.

The portal is the system of record for the program. There is no external CFP tool to synchronize with; everything the team currently keeps in spreadsheets about speakers moves here.

### 1.1 Goals

| Goal | How the design meets it |
|---|---|
| No spreadsheet | Every speaker fact and every status lives in the portal; CSV is an export, not a working document |
| Two-way transparency | Speakers see the team's checklist for them, not just their own |
| Timezone safety | All times stored in UTC, rendered in the viewer's zone; organizers can preview any speaker's local time before confirming a slot |
| Lightweight for speakers | Every content field is optional markdown; a title and two sentences is a complete listing |
| Customizable process | Checklists are templates organizers edit in the portal, not code |
| One source for the website | The conference site embeds a widget; publishing in the portal updates the site |
| Reusable next year | Everything is scoped to a conference (edition); templates and settings clone forward |

### 1.2 Scope

**In:** session and presenter management, invitations, speaker self-service profile and session editing, two-sided checklists with reminders, scheduling with room assignment, public schedule and speaker embeds with calendar feeds, promo asset storage, video upload and post-production tracking for pre-recorded sessions, CSV/JSON export, pretix registration sync.

**Out:** call for proposals and review, automated transcription/translation/video rendering (uploads and tracking are in; processing is manual), speaker certificates, translation of the portal UI, Discord bot automation (channel and role management stay manual; an estimate is in §12.2), payments or honoraria.

---

# Part 1 — How it works

## 2. The speaker's journey

A speaker never fills in a form they didn't ask for. The whole journey is: get invited, accept, tell us about your session, do a short list of things, show up.

### 2.1 Invitation

An organizer adds the session and the person, writes a personal note, and sends the invitation. The email carries a link that is just for that speaker; clicking it creates their account. From then on they sign in with a one-time code emailed to them, or with a password if they set one: the welcome page offers to set one and the dashboard asks until they have or dismiss it.

### 2.2 The dashboard

The first thing a speaker sees after accepting, and the page they come back to. Two lists side by side:

- **Your to-dos** — update bio, read the guide, register, join Discord, confirm the slot, share materials, tech check. Items the portal can verify tick themselves (the bio is there; the pretix order was found).
- **What we're doing for you** — the team's list for this speaker, with who is on each item. A speaker can see "promo materials — in progress, Lena" without emailing anyone.

Reminders go out by email a week, three days, and a day before anything is due, in the speaker's own timezone.

### 2.3 Their session

Every content field is optional markdown: summary, outline, prerequisites, audience. A title and two sentences is a complete listing; a full outline is welcome. Co-presenters and panelists are listed with their roles. Nothing here is visible to the public until the team publishes the session.

### 2.4 Their schedule

The schedule in the speaker's own timezone, their sessions highlighted, visible before the program is public with a "not yet public" badge. Each session has an add-to-calendar link, and there is a personal calendar feed that stays correct if a slot moves.

### 2.5 Proposing a session, and adding one

> **Being built.** Decided on 21 September 2026 and extended on 23 September; the proposal side is new work rather than part of the original proposal.

The 2026 edition invites its speakers, and the portal was built for that. An edition can also open the door: while proposals are open, anyone with a portal account can propose a session at `/speakers/propose/`, which is the link to put on the conference site.

The form is one page: who you are, and what you would like to give. It creates real rows from the start, a presenter and a session in a **proposed** status, so nothing about it is a draft held in a form somewhere. Organizers read it and click approve or reject; the review is deliberately informal, with no notes on the proposal, because the answer is yes or no rather than a conversation.

Submitting sends the proposer a receipt and the organizing side a notice, at `SpeakerSettings.organizers_email` where the edition has set one and the staff accounts where it has not.

**Approving is the acceptance path an invitation takes**: the presenter is confirmed on the session, their checklists are created and dated from the approval, the session goes on to confirmed when nothing blocks it, and from then on it is an ordinary session. **Rejecting** keeps the rows and sends a short, kind note with no reason, and it is not final: a rejected proposal can be approved later from the answered list, which is what happens when a cancellation frees a slot. The proposer can **withdraw** while nobody has answered: the rows stay, the proposal leaves the organizers' queue, and the proposer can go on editing it and **send it again**, which returns it to pending and re-notifies as any new proposal does. A pending proposal is capped at three per person per edition.

Someone whose proposal is pending or turned down has an account and a presenter row, but no session of the conference's, so the speaker area is not theirs: the pages check that they are actually on the program.

**A speaker already on the program proposes too.** One door, whoever is knocking: the organizers decide what is on the program, and a second way in made the speaker's own pages contradict each other. What they are spared is the "About you" half, which they filled in at onboarding; the proposal then follows the ordinary path.

---

## 3. Running the program as an organizer

### 3.1 Sessions

One list for everything that will be on the schedule — workshops, panels, PyJam performances, and also the opening, breaks, and closing. Status moves from draft, to invited, to confirmed, to scheduled, to published, and any of them can be cancelled. A speaker liaison sees only the rows assigned to them.

### 3.2 A presenter, in one place

Everything about one person: their to-dos, the team's to-dos for them (assignable and tickable here), sessions, invitation history, promo assets, and an activity log showing what the portal did automatically — "pretix order paid → registration marked done".

### 3.3 The checklist board

Presenters down the side, every checklist item across the top, one colour per cell. Sort by most overdue and the people who need a nudge float to the top. Tabs switch between the speaker side, the organizer side, and post-production. This replaces the spreadsheet's status columns.

Checklists are templates the team edits in the portal — items can be renamed, reordered, added, or removed per role, and the templates carry forward to next year.

### 3.4 Building the schedule

A grid with the rooms as columns and 15-minute steps as rows. Unscheduled sessions wait on the side and are dragged in; a "+ program item" button drops an opening or break straight onto the grid, spanning every room. Conflicts — two sessions in one room, a presenter double-booked — are highlighted where they happen.

The timezone switcher shows the grid as a specific presenter would see it, which is how "we scheduled her at 3 a.m." gets caught before the confirmation email.

### 3.5 Publishing

The program is internal until the team flips it to published. Each session is published individually and only once it is scheduled; a presenter's bio becomes public only through a published session. A preview link lets the conference website be built against the draft program.

## 4. PyJam performances

PyJam sessions are pre-recorded. The performer uploads the video; the team post-produces it and publishes to YouTube for a scheduled premiere or watch party.

### 4.1 The performer

> **Being built** (M3b). Task 5.2 (29 September 2026): the upload panel on the performer's session page, with resume, the current version and the length bar, and the organizer's per-session file list with download links and reviewer notes. The duration probe (5.3, same day) fills the length bar within seconds of an upload, and the post-production board (5.5) tracks the pipeline; what remains of the proposal is the performer's own view of it, which today is their checklist's "What we're preparing for your video" list.

Same dashboard as any speaker, plus an upload panel: the video goes straight to storage in chunks and resumes if the connection drops, and the panel shows the duration against the length limit. The performer's second list is "what we're doing with your video", so they can watch it move through transcription, translation, and the final cut. When the final cut is ready, an "approve the final cut" item opens for them.

### 4.2 Post-production

> **Built** (M3b, task 5.5, 30 September 2026). Cells link to the item page, where the assignment happens; the board itself stays light.

The third tab on the checklist board: sessions down the side, pipeline items across — MC intro and outro, quality review, length check, transcribe, review transcript, translate (one column per language), title card and final cut, publish to YouTube. Items backed by a file complete themselves when the file is uploaded. The length check turns red and blocks the row when a video is over the limit. Every item is assignable, and the template is editable like all the others.

## 5. The conference website

The website embeds a widget served by the portal. When the team publishes in the portal, the site updates; there is no rebuild.

- The schedule shows in the visitor's timezone, with breaks as bands and sessions as cards.
- Every session has a subscribe link — a calendar feed for that one session, so a reschedule updates the attendee's calendar automatically.
- Visitors can star sessions and subscribe to just those, with no account.
- Unpublished sessions simply aren't there; no "TBA" rows.

The website already depends on the portal for `stats.json`, so this adds no new dependency. The widget is long-cached behind the CDN and shows a link to the portal's schedule page if the API is unreachable.

## 6. The workflows side by side

```
Organizer                          Speaker / performer                   Portal (automatic)
─────────                          ───────────────────                   ──────────────────
add session + presenter
send invitation ──────────────►    accept, account created  ────────►    checklists instantiated
                                   update bio, session details ──────►   "bio updated" ticks
                                   read speaker guide ─────────────►     "read guide" ticks
                                   register on pretix ─────────────►     webhook → "registered" ticks
send onboarding, registration info
prepare promo materials ────────►  sees "in progress, Lena"
schedule on the grid ───────────►  sees slot in own timezone ─────►      "scheduled" ticks; conflicts checked
send schedule confirmation ─────►  confirms slot
   (PyJam) ◄────────────────────── uploads video ─────────────────►      duration checked; "uploaded" ticks
   post-produce, assign items ──►  sees pipeline progress
   publish to YouTube
publish program ────────────────►  card goes public ──────────────►      website widget + calendar feeds update
```

---

# Part 2 — How it is built

## 7. Roles and access

| Role | Sees | Does |
|---|---|---|
| **Organizer** | everything in the edition | add sessions and presenters, invite, schedule, publish, edit checklist templates, complete organizer tasks |
| **Speaker liaison** (volunteer) | only the presenters and sessions assigned to them | edit those presenters' details on their behalf, complete organizer tasks for them, send reminders |
| **Presenter** (speaker, panelist, moderator, host, performer) | their own profile and sessions, co-presenters' names and bios, the schedule, their checklist, and the organizer checklist for them | edit own profile and session content, tick own checklist items, upload their video |
| **Public** | published sessions and presenters through the widget and API | read |

Liaisons seeing only their assigned speakers is a deliberate change from a shared spreadsheet where every volunteer sees every speaker's email and status. It is enforced in database queries and covered by the portal's tenant-isolation test suite.

Speakers sign in with a one-time code emailed to them. A password is optional: the welcome page offers to set one, the dashboard asks until they do or dismiss the reminder, and the usual reset flow works for those who have one.

### 7.1 Permissions and teams (M2b)

> **Not built.** Access today is `is_staff` and `is_superuser` plus team membership and item assignment, which is what this section is meant to replace.

The table above says what each audience does. This section says how the portal decides, and replaces the mechanism the portal grew up with.

**Where access comes from today.** Four mechanisms coexist and only one is a permission. The Django `is_staff` / `is_superuser` flags mean "organizer" everywhere: the admin mixins, the `is_organizer` context flag, the speaker-side `is_speaker_organizer`, sponsorship management, queryset scoping, the "who gets internal emails" queries and a dozen template checks; `is_superuser` alone gates conferences and Start next year. The volunteer `Role` model (Admin, Staff, Vendor, Volunteer) is assigned on the review form and used for two things only: routing internal notification emails to Admin and Staff, and picking the admin variant of the onboarding email; it grants no access. Object relations (team leads, `Presenter.liaison`, item `assignee` / `team`, "approved volunteer of this edition") are data-model checks and stay that way. The one real permission is `portal_account.view_maintenance`, granted by the "Infra maintainers" group and read through `has_perm`; it is the pattern to generalise.

**Principle.** Every "may this user do this" check goes through `user.has_perm("app.codename")` in Python and `{% if perms.app.codename %}` in templates, wrapped in a named predicate in each app's `permissions.py`. Teams are the grant vehicle; permissions are how access is read. `is_superuser` keeps Django's built-in bypass as break-glass; `is_staff` survives only for signing in to the Django admin.

**Teams grant, an auth backend derives.** `Team` gains `permissions` and `lead_permissions` (many-to-many to `auth.Permission`), set by the portal admin when creating a team, editable afterwards, cloned by Start next year. Rather than syncing users into global `auth.Group` rows (teams are per edition, groups are not, so last year's Sponsorship team would keep this year's rights until something removed them), a small authentication backend implements `get_all_permissions` by reading the user's approved memberships and leaderships in the **active** edition's teams. Leads get the lead set plus the team set. Nothing is ever stale and the edition switch revokes by itself. The backend also implements `with_perm` so recipient queries (`User.objects.with_perm(...)`) find team members. Baseline grants, computed the same way and tied to no team: an approved volunteer of the active edition may read sponsors and open their own volunteering tasks; a presenter gets the speaker side.

**The catalogue.** Built-in `add` / `change` / `delete` / `view` are reused where they fit; custom ones are declared in `Meta.permissions` on the model that owns the feature.

| Area | Permission | Replaces |
|---|---|---|
| Conferences | `portal.view_organizer_dashboard` | `is_organizer` for Organize and its rail |
| | `portal.change_conference`, `add_conference`, `delete_conference`, `portal.start_next_year` | superuser |
| Volunteers | `volunteer.view_volunteerprofile` | `is_staff` on the list and other people's profiles |
| | `volunteer.review_volunteerprofile` | staff on the review form (leads keep their own team via the object check) |
| | `volunteer.add_team`, `change_team`, `delete_team` | `VolunteerAdminRequiredMixin` |
| | `volunteer.receive_volunteer_notifications` | the Admin / Staff roles, i.e. the whole reason `Role` exists |
| Sponsorship | `sponsorship.view_sponsorshipprofile` | approved volunteer of the edition (kept as the baseline grant) |
| | `sponsorship.add/change/delete_sponsorshipprofile`, `sponsorship.send_invoice` | organizer |
| | `sponsorship.view_unconfirmed_sponsors` | superuser in the list filter |
| | `sponsorship.add/change/delete_sponsorshiptier` | organizer |
| | `sponsorship.receive_sponsorship_notifications` | role-based routing in the sponsorship tasks |
| Speakers | `speakers.manage_program` (sessions, invitations, presenters, scheduling, publishing, pretix link) | `is_speaker_organizer` |
| | `speakers.view_program` (read every session and presenter; liaisons stay scoped through `Presenter.liaison`) | organizer |
| | `speakers.change_checklisttemplate`, `speakers.change_handbook` | organizer; split out because it is content-team work |
| | `speakers.change_speakersettings` | organizer; separate because the row holds pretix secrets |
| | `speakers.assign_checklistitem` | "organizer or the presenter's liaison" (the liaison half stays relational) |
| | `speakers.liaise_presenters` (may be picked as a liaison) | "staff or approved volunteer" |
| Media (M3b) | `speakers.view_mediaasset`, `add_mediaasset`, `change_mediaasset`, `delete_mediaasset` | "organizers any kind" in §8.8; performers keep raw video on their own sessions relationally |
| | `speakers.publish_session_video` (YouTube URL, publish time, premiere location) | organizer; narrower than `manage_program` so Design can close the pipeline |
| Promo (M5) | `speakers.view/add/change_promoasset` | organizer |
| Maintenance | `portal_account.view_maintenance` | already a permission |

Ticking checklist items is never a permission: the assignee, an approved member of the owning team, the presenter's liaison, or the presenter themselves, as today.

**Default permission sets** (presets the admin picks from when creating a team; every team's set stays editable):

| Team | Members | Leads add |
|---|---|---|
| Organizers (core) | everything above except `delete_conference` and `start_next_year` | those two |
| Volunteer coordination | view and review volunteer profiles, manage teams, volunteer notifications | |
| Sponsorship | sponsor add / change / delete, send invoice, unconfirmed statuses, tiers, sponsorship notifications | |
| Program | manage program, view program, assign items, liaise, templates, handbook | `change_speakersettings` |
| Speaker liaisons | liaise presenters, assign items | |
| Design | view program, view / add / change media assets, publish session video; promo assets when they exist | delete media assets, assign items |
| Website, Content, Social media | none; work reaches them through task assignment, which is relational | |
| Infra maintainers | view maintenance (unchanged) | |

**What goes away.** `Role`, `RoleTypes` and `VolunteerProfile.roles`, with a data migration mapping Admin and Staff to membership in that edition's Organizers team (Vendor and Volunteer granted nothing). Every `is_staff` / `is_superuser` check in portal logic: the mixins in `common/mixins.py`, the context-processor flags, the speaker predicates, the sponsorship viewer mixin and filter, the recipient queries, the liaison dropdown and the template checks. Rosters, profiles and emails show team names and a Lead badge instead of roles. Sample data and test factories grant through teams.

**Risks.** Today every staff account is an organizer everywhere; after the switch, people must actually be on a team or they lose access on day one, which is why the migration builds an Organizers team from today's staff users. Liaison and team-member checks stay object-level by design, so this does not simplify them. The superuser bypass must stay or the first admin locks themselves out.

---

## 8. Data model

Every model belongs to a `portal.Conference` — the portal's existing per-edition tenant — so PyLadiesCon 2027 is a new conference row with the same code.

```
portal.Conference
 ├── SpeakerSettings (one row: the module's switch and the edition's defaults)
 ├── SessionType ──── PresenterRole (which roles a type allows)
 ├── Session ──────────────── SessionPresenter ──── Presenter ──── User (optional)
 │     │                        (role, order)          │
 │     ├── ScheduleSlot ──── Room                   └── ChecklistItem (owner=SPEAKER)
 │     ├── MediaAsset (pre-recorded sessions)
 │     ├── PromoAsset (M5, not built)
 │     └── ChecklistItem (owner=ORGANIZER; per presenter or per session)
 ├── ChecklistTemplate ──── ChecklistTemplateItem
 ├── ReadinessGate (what a checklist line can wait for, §9.3a)
 ├── Invitation
 ├── Handbook (versioned) ──── HandbookReadReceipt
 ├── ReminderLog
 └── ActivityLog
```

A presenter's pretix order is reached through `Presenter.pretix_order`; the
`PretixOrder` model itself belongs to the `attendee` app, not to this one.

### 8.1 Session

One row per **anything that appears on the schedule**: workshops, panels, PyJam performances, and also the opening, closing, breaks, and social slots. There is no separate "program item" type; a break is a session with no presenters.

| Field | Notes |
|---|---|
| `kind` | A **`SessionType` row** per edition, not an enumeration: the list above became the seeded defaults (`WORKSHOP` · `PANEL` · `PYJAM` · `TALK` · `LIGHTNING`, and the program types `OPENING` · `CLOSING` · `KEYNOTE` · `ANNOUNCEMENT` · `BREAK` · `SOCIAL` · `OTHER`), and organizers add their own on the "Types and roles" page without a deploy. The row carries what the code used to switch on: `is_content`, the default duration and delivery, whether it spans all rooms, and which `PresenterRole` rows it allows. |
| `delivery` | `LIVE` (default) or `PRE_RECORDED`. PyJam defaults to pre-recorded; any kind can be switched. Pre-recorded sessions get the media pipeline (§8.8) and a post-production checklist (§9.7). |
| `is_content` | read from the type row: a content type needs at least one presenter to be confirmed; a program type can be confirmed with none (a break) or with hosts (the opening) |
| `title` | required — the only required field |
| `summary_md`, `outline_md`, `prerequisites_md`, `audience_md`, `notes_md` | Markdown, all optional |
| `level`, `language`, `duration_minutes` | optional; duration defaults from kind (workshop 90, panel 60) |
| `video_length_limit_minutes`, `youtube_url`, `youtube_publish_at`, `premiere_location` | pre-recorded only. `premiere_location` is `DISCORD` (watch party in the slot's room) or `YOUTUBE` (YouTube Premiere at the slot time), defaulting from the edition's speaker settings; it changes what the public card links to and nothing else, so the team can decide per session or late. |
| `status` | `DRAFT` → `INVITED` → `CONFIRMED` → `SCHEDULED` → `PUBLISHED`, plus `CANCELLED`. Program kinds skip `INVITED`. |
| `is_public` | explicit publish switch; nothing reaches the website without it (§11.5) |
| `slug` | stable public identifier used in URLs and calendar feeds |

Markdown is rendered server-side and sanitized. The source is stored, never the HTML.

### 8.2 Presenter

The person, independent of any session. One presenter can run a workshop and sit on a panel.

| Field | Notes |
|---|---|
| `user` | nullable. Linked when the invitation is accepted; a presenter can be added and scheduled before they ever log in |
| `display_name`, `pronouns`, `bio_md`, `headshot`, `location`, `timezone` | `timezone` drives reminder timing and the speaker's own schedule view |
| `email` | invitation and reminder target; unique per conference |
| `website_url`, `github_username`, `mastodon_url`, `linkedin_url`, `bluesky_username` | the links shown on a public presenter card |
| `is_public` | presenter-controlled: opt out of a public bio page while still being named on the schedule |

### 8.3 SessionPresenter

Links a presenter to a session with a `role` (a `PresenterRole` row; the seeded ones are `PRESENTER`, `PANELIST`, `MODERATOR`, `HOST` and `PERFORMER`, and a type only allows the roles it lists), an `order` for display, and `confirmed_at`. Panels are sessions of kind `PANEL` with panelists and a moderator; nothing special is needed for them. Panels are assembled by organizers.

### 8.4 Invitation

An organizer invites a presenter to a specific session (or, for panelists, to the conference generally) with a personal note. The email carries a single-use, expiring token. Accepting it creates or links the account, confirms the presenter on the session, and instantiates their checklist. `sent_at`, `opened_at`, `accepted_at`, `declined_at` are recorded so the sessions list can show "invited 9 days ago, not yet accepted".

### 8.5 Scheduling

> **Built** (M3, 3 October 2026): the models and the validation below, in `ScheduleSlot.clean()` and `ScheduleSlot.presenter_clashes()`. The editor and the schedule views are §10, not yet built.

**Room** — `name`, `discord_id`, `url`, `kind` (`STAGE`, `VOICE`, `TEXT`, `FORUM`), `is_active`. Deliberately generic: for an online edition a room is typically a Discord channel, created on Discord by hand and recorded here, but nothing else in the portal cares where a room actually is.

**ScheduleSlot** — one per session: `room` (nullable — null means *every room*, so the opening or a break spans the whole grid), `start_utc`, `end_utc`. `end_utc` defaults from the session duration.

Validation: no two slots overlap in one room (an every-room slot conflicts with everything in its window, except other program-kind bands); a presenter in two overlapping slots is flagged as a warning, not blocked — a moderator moving between rooms is legitimate. A session still waiting for an answer (`PROPOSED`, `REJECTED`) cannot hold a slot at all, which is what makes it safe for the overlap rules to look through those statuses on the other side; a cancelled session keeps its slot as a record, freed for others. The checks are application-level: two organizers saving overlapping slots in the same instant can both pass and both commit. The database-level guarantee would be a Postgres exclusion constraint on (conference, room, `tstzrange(start_utc, end_utc)`) via `btree_gist` — worth adding once the editor makes concurrent edits plausible.

All times are stored in UTC. `SpeakerSettings.conference_timezone` (one row per conference) is only the organizer's default display; the conference itself has no timezone.

### 8.6 Promo materials, and what the team shares with the speaker

> **Built** (M3b, 30 September 2026), as part of `MediaAsset` rather than a model of its own. The `PromoAsset` model this section once proposed is not needed.

Promo materials belong to a **session**, not a person: a speaker on a panel and a workshop gets a poster for each. And there are several per session: square, landscape and vertical images, a video, a gif. So they are `MediaAsset` rows of kind `PROMO` with a free **`variant`** label ("square", "landscape", "vertical", "video", "gif", or whatever next year's formats are; the upload panel suggests those five). Versions count per kind, language and variant, so re-uploading the square poster supersedes the old square poster and nothing else. Organizers upload them on the session's Files section like any other file (the team's Canva workflow produces them; the presenter list exports to Canva's bulk-create CSV); the design team's bulk download (5.6) collects them.

**Sharing is a flag, not a kind.** Every file the team uploads is the team's until an organizer marks it **shared with the speaker** (`MediaAsset.shared_with_speaker`, a button on the file's row). A shared file appears on the speaker's session page under "Files from the team", with the newest shared version of each kind, language and variant, a download link, and no reviewer notes: those stay with the team. Unsharing takes it back. The speaker hears about newly shared files in the daily digest, when there are any (§13.2). A presenter may fetch their own raw video and whatever is shared; nothing else, however they got the link. Two seeded organizer lines follow the flag: "Promo materials prepared" completes when the first promo file is on the session, "Promo materials shared with presenter" when the first one is shared. The performer's "Approve the final cut" waits until the processed video is not only in but shared, since that is when they can watch it.

Generating cards in the portal is a possible later addition.

### 8.7 Handbook

The speaker guide, versioned. Reading it records a `HandbookReadReceipt`; publishing a new version re-opens the "read the speaker guide" item for everyone who read the old one.

### 8.8 MediaAsset

> **Being built** (M3b). Task 5.1 (29 September 2026): the multipart upload backend, `MediaUpload`, the JSON endpoints, versioning and `asset_ready`. Task 5.2 (same day): the browser panel with resume, the performer's video card, the organizer's file list with notes and downloads. Task 5.3 (same day): the duration probe on the `media` queue, with the failure written on the asset. Task 5.4 (same day): the final-cut approval waits for the processed video; the rest of the session-scoped checklist was already in place from the checklist work. The post-production board (5.5) is next.

For pre-recorded sessions, one row per file that moves through post-production:

| Field | Notes |
|---|---|
| `kind` | `RAW_VIDEO` (performer upload) · `INTRO` · `OUTRO` (MC recordings) · `PROCESSED_VIDEO` (final cut) · `TRANSCRIPT` · `TRANSLATION` · `TITLE_CARD` · `THUMBNAIL` · `PROMO` (§8.6) · `OTHER` |
| `file` | Digital Ocean Spaces, private; presigned upload and download |
| `language` | for transcripts and translations, one row per language |
| `variant` | which of several files of one kind: promo materials come as square, landscape, vertical, video, gif (§8.6) |
| `shared_with_speaker` | the team's flag that puts the file on the speaker's session page and lets them fetch it (§8.6) |
| `version` | increments on re-upload, per kind, language and variant; old versions kept until deleted |
| `duration_seconds`, `probe_error` | probed server-side after upload (`ffprobe` over a presigned link, on the media queue); drives the length-limit check. When the probe cannot answer, the reason is on the asset and on the page |
| `status`, `notes_md` | `UPLOADING` · `READY` · `FAILED` · `SUPERSEDED`; reviewer notes ("audio clips at 4:10") |

Performance videos are routinely several gigabytes, so the browser uploads directly to object storage in chunks using presigned multipart URLs, with per-part retry and resume. The portal finalizes the upload and records the asset. Performers can upload raw video for their own sessions; organizers upload any kind.

#### The speaker side is a switch

The organizer side of everything above (files on a session, the board's tab, exports, previews) is always on once the portal has a bucket. What speakers see is a per-edition switch on the speaker settings, **off by default**: with it off, a speaker's session page has no Files tab and no upload panel, a presenter may neither upload nor fetch, and the team gathers videos by other means and uploads them on the performer's behalf, which completes the same checklist lines. The switch lets the media series merge and run dark for speakers while the team tries it with real files.

#### A title for each file

> **Built** (30 September 2026, task 5.9).

A file is named by its kind, language and variant ("Promo material (square)", "Transcript (en)"), which says what it is but not what it is about. Organizers want to write "Poster for the panel, from the Canva template" or "Final cut with the new intro" once, and not again for every version or format of the same thing.

**The title belongs to the line, not the version.** A *line* is one kind and language on one session; its variants and versions are the same thing in different shapes and ages. The title is therefore asked for the first time a line gets a file, carried forward onto every later version and variant, and editable in one place. Stored as `MediaAsset.title` (short, one line, 200 characters) and copied rather than joined: completing an upload with no title takes the newest title on the line, so the row always carries its own words and the page, the bulk-download manifest and the CSV need no lookup. Editing the title updates every row on the line at once, so old versions read the same as the new one.

**Where it is asked.** The upload panel gains an optional *Title* field on both sides: the organizer's, where it is prefilled from the line the chosen kind and language already have (a page-level map of line titles, read by the panel's script when the kind or language changes, and left alone once the person has typed), and the performer's, where "take 2, quieter room" is welcome but not required. The start endpoint takes it, `MediaUpload` carries it, `complete_upload` writes it or inherits it.

**Where it shows.** The organizer's file list puts the title on the group header next to the kind and variant badges, with a small edit form that swaps the group in place (htmx, like the note). The speaker's "Files from the team" leads with the title when there is one and the kind and variant in a badge after it; without one, the kind as today. The post-production board's video column and the CSV export carry it, and the manifest of the bulk download will once task 5.6 lands.

**What it is not.** Not the reviewer's note, which is per version and internal. Not a description of the session. Not required, so an upload never waits on it. A separate `MediaLine` model that groups assets would be the more structural home for a per-line attribute, and is the shape to move to if lines ever gain more of their own (an owner, a deadline); for one short field, a copied column is the smaller change and keeps every reader one query.

#### Deleting a file

> **Built** (2 October 2026).

Files are kept until someone deletes them: a cancelled session keeps everything it had, since a cancellation is often undone and the recording is the hard part to get back. Deleting is explicit, per *file*, and takes **every version** of it: a file is a line (kind, language and variant on the session), its versions are the same thing at different ages, and a page that let someone delete v2 and keep v1 would be offering a choice nobody makes on purpose. The rows go in one transaction, with the finished upload rows that pointed at them; each row's object, the thumbnail beside it and an admin-attached file go from storage once that transaction commits, through the same receiver the admin's cascade runs through, so the two paths cannot drift and a rollback never leaves a row without its file. A machine transcript made from a video on the line goes with it, since its line is keyed to the video's own row and a draft of a file that is gone has no reader; a reviewed transcript a person uploaded stays. The session's activity log records what went, with the file names, and who did it.

**Who.** Organizers may delete any line from the session's Files section. A performer may delete their own raw video from their session page, and only while every version of it is their own upload: once the team has put a version there on their behalf, the line is the team's to take away, and the page offers nothing. The usual gates apply (the speaker side's switch, a presenter on an accepted session). A video whose transcription is still running stays until the job is done, because the job would otherwise write a transcript for a file that is gone.

**The confirmation.** One dialog per page, opened by the row's *Delete every version* button; it shows what will go and asks the person to type the file's name as the row shows it (the newest ready version's). The button stays disabled until the name matches, and the view checks it again: a name that does not match deletes nothing. Typing a name rather than clicking "yes" is the point, since the file is routinely the only copy of a performance.

**What the admin's session delete does.** Deleting a `Session` row in the Django admin cascades to its assets, so every object and thumbnail goes with it, and an upload still in flight is aborted so its parts are freed. The design permissions table lists `delete_mediaasset` for the Design team's leads; until the permissions refactor lands, deleting follows the organizer gate like the other file actions.

#### Previews

A file row, and the speaker's "Files from the team" card, carry a closed "Preview" fold for the files a browser can show itself: images, video and audio, decided from the upload's content type with the file name as a fallback. Opening it loads the file from the bucket through a second presigned link that says *inline* rather than *attachment* and carries the file's type; images load lazily, video and audio not until play, and a multi-gigabyte video then streams by range requests, so nothing is fetched in full. A transcript, captions file or other small text file shows as plain text, fetched through the portal rather than by a signed link (the same permission check, no CORS rule, a few kilobytes), in the fold and in a new tab. Everything else, including an HTML file uploaded as "other", only downloads. The file rows, the speaker's files, the board's video column and the sessions list also carry a **thumbnail** (task 5.8, built 30 September 2026): when an image or video lands, the media worker scales the image with Pillow or takes a frame a few seconds in with ffmpeg, stores it as a small JPEG next to the original, and the pages show it through a redirect to an inline link, so a list of thirty sessions costs no signing to render. Audio gets an icon. A thumbnail that could not be made says why on the row and never holds the file up.

#### Where files live in the bucket

Every object is keyed by edition, session and kind, so the bucket itself reads like a folder tree:

```
speaker-media/2026/<session-slug>/raw_video/<upload id>/<original filename>
speaker-media/2026/<session-slug>/transcript/<upload id>/<original filename>
```

The upload id segment is what makes a re-upload a new object instead of an overwrite; the version number is assigned when the upload completes and lives on the row, not in the key. The row is the source of truth for everything else too: a session's slug can change after its first upload, and old objects keep the old slug. Nothing reads the bucket by listing it.

#### Bulk download (post-production)

> **Built** (30 September 2026, task 5.6), with two changes from the design below made on trying it: the zip is the first choice on the page and the script the advanced one, and the browser "download to a folder" path was dropped, since choosing a folder in a browser dialog read as odd. The sessions in the scope are an explicit choice ("every session with files" or "only these", a filtered checkbox list grouped by type), so a stray click narrows nothing.

The people who edit the videos, design the title cards and cut the final versions work on their own machines, in their own tools, and they want *everything* for the edition on local disk, not one file at a time from a web page. A pull of an edition's raw video is tens of gigabytes across dozens of files, which rules out the two obvious shapes: a zip built on the server doubles the storage and ties up a worker and its disk for an hour, and a zip streamed through Django holds a web worker for the whole transfer and cannot resume when the connection drops. The bucket already knows how to serve large files with range requests and resume; the portal's job is to hand out the list of what to fetch and where to put it.

**The export.** An organizer picks a scope on the sessions list or the post-production board (§4.2): the edition (the active one by default), the kinds (raw video by default), an optional language, the sessions currently filtered, and whether to include superseded versions (latest `READY` only by default) or only files newer than their last export. The portal answers with one presigned download link per asset and a local path for each, laid out the same way as the bucket, without the upload id and with the version in the file name so two versions can sit side by side:

```
pyladiescon-2026/<session-slug>/raw_video/v2-<original filename>
pyladiescon-2026/<session-slug>/transcript/v1-en-<original filename>
pyladiescon-2026/<session-slug>/promo/v1-square-<original filename>
pyladiescon-2026/manifest.csv
```

`manifest.csv` carries what the file names cannot: session title, presenters, kind, language, version, duration, size, when it was uploaded and by whom, and the reviewer notes. Editors sort and search that in a spreadsheet; the folders stay predictable for scripts and for the editing software's media bins.

**Three ways to fetch it**, all from the same export:

1. *Download to a folder*, in the browser. On Chromium browsers the page asks for a local folder (the File System Access API), then streams each object straight from the bucket into that folder with the layout above, with per-file progress, retry, and skip-if-already-complete so a second run only picks up what is missing. No tooling to install; this is the button most people will use. Other browsers do not offer a folder picker and get option 2.
2. *A download script*. A shell script with one resumable `curl` line per file (`-C -`, `--create-dirs`) and the manifest embedded, for anyone on a terminal, plus an `aria2c` input file for parallel transfers. Runs unattended and resumes after an interruption.
3. *A zip*, only for small bundles. Transcripts, title cards and thumbnails for an edition are a few hundred megabytes at most, and a designer expects a zip. When the selection is under `SPEAKER_MEDIA_ZIP_MAX_BYTES` (1 GiB by default) the portal offers to build one: a worker task streams the objects into a zip stored under `speaker-media/exports/`, and the person gets a link when it is ready. A lifecycle rule deletes exports after 7 days. Above the cap the option is not shown.

**Links and their lifetime.** A presigned link is a bearer credential: anyone holding it can fetch the object until it expires. Bulk links live longer than the one-hour page links (`SPEAKER_MEDIA_BULK_URL_TTL`, 12 hours by default, enough for a 100 GB pull on a home connection) and the export page says so. The script and the manifest are therefore treated like a credential: the page warns not to share them, and every export is recorded as a `MediaExport` row (who, when, scope, file count, total bytes, expiry) so the Maintenance section can answer "who pulled the 2026 videos, and when". The links in any email the portal sends about an export are withheld from the email record the same way invitation links are (§2.23).

**Who.** Organizers, the same rule as uploading any kind; presenters never bulk download. Once the permissions catalogue lands (task 3.7) this becomes `speakers.view_mediaasset`, which is what puts the Design and Communication teams on the export page without making them program managers.

**The other direction.** Editors bring processed videos, transcripts and title cards back. That stays per file through the upload panel for now; a "bulk upload from a folder" would read the same layout and manifest in reverse and is not designed here.

**The escape hatch.** For a post-production lead who wants to `rclone sync` the whole edition and keep it in sync as new uploads arrive, DigitalOcean can issue a Spaces key with read-only access to just the media bucket. That works today, needs no portal code, and is the most efficient way to move 100 GB, but the key sees every edition and every kind and nothing in the portal records what it fetched, so it is an operations procedure for one trusted person (documented in the deployment guide), not a feature.

**Cost.** Spaces includes 1 TiB of outbound transfer a month and charges a cent per GiB beyond it, so a handful of full pulls of an edition costs nothing extra. The export page shows the total size of the selection before anyone starts.

#### Machine transcription

> **Built** (30 September 2026, task 5.7), as designed below. The library and the model enter any image built with a non-empty `WHISPER_MODEL`, which the Dockerfile defaults to `small` so the platform build (no build arguments) has an engine; `compose.yml` sets it empty, so local builds and CI carry neither, but the production web process does carry them, one image serving every process; an image built with it empty offers no transcription and says so.

The "Transcribe" item on the post-production checklist completes when a transcript asset exists for the session's language (§9.7), so a worker job that writes one is the whole feature from the checklist's point of view: the item ticks itself, "Review transcript" stays a person's job, and the reviewer's corrected file goes up through the ordinary panel under the draft's variant (the panel lists the variants on the session), which makes it the next version of that video's transcript. The job is a draft-maker, never the last word.

**What triggers it.** A raw video becoming `READY` (`asset_ready`), when the edition's speaker settings have *machine transcription* switched on (off by default) and the session has no transcript for its language that a person made. A new raw video version re-runs it only while the latest transcript is still a machine one; a reviewed transcript is never overwritten by a re-upload. An organizer can also start it by hand from a video's row in the Files section ("Transcribe this"), including on the processed video, and retry a failed run from the same place.

**What it produces.** One `MediaAsset` of kind `TRANSCRIPT` in the session's language (or the language the engine detected, when the session has none), as **WebVTT** with cue timings: what YouTube accepts as captions and what a browser plays with `<track>`, and easy to read as text. It is uploaded to the bucket with a single put, recorded like any other asset (the next version for its kind, language and variant, the previous `READY` one superseded, `asset_ready` sent; the variant is the video's file name stem and its pk, so each video has its own transcript line), with `uploaded_by` empty and a new `generated_by` field naming the engine and model (for example `faster-whisper/small`), so the file list and the review item can say "machine draft" rather than pass it off as a person's work. Whisper's translation mode only targets English, so translations stay a person's job; a later job could draft them with a language model, and that is a separate design.

**How it runs.** A Celery task, `transcribe_asset_task`, on its own queue:

1. Records a `TranscriptionJob` row (video asset, engine, `QUEUED`), which is what the Files section shows while it runs ("Transcribing, started 4 minutes ago") and what "Retry" acts on.
2. Extracts the audio without touching the video on disk: `ffmpeg` reads the presigned video URL and writes raw 16 kHz mono 16-bit samples to a temporary file (about 57 MB for a 30-minute set, gone with the job). Raw samples rather than a compressed file so the engine decodes nothing itself: on trying it, the engine's own decoder (PyAV) turned out to be the one piece whose versions drift under it.
3. Hands the audio to the configured engine and gets back timed segments.
4. Writes the VTT, uploads it, records the asset, marks the job `DONE`.
5. On any failure marks the job `FAILED` with the error, logs it to the session's activity, and leaves the checklist item open. Never silent: a missing `ffmpeg`, a missing model, an exhausted API quota all show on the page.

**The engine: Whisper in the worker, nothing hosted.** Decided 29 September 2026: transcription runs inside the portal's own worker with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper on CTranslate2, CPU, int8), and no audio leaves the portal's infrastructure. A hosted API was considered and set aside: it would be faster and better at hard audio, but it sends performers' recordings to a third party, needs a paid key, and would have to be disclosed in the performer guide. The engine sits behind a small interface (`speakers/transcription.py`: `transcribe(audio_path, language) -> segments`) so a different engine could be added later without touching the pipeline, but none is planned. `SPEAKER_TRANSCRIBE_MODEL` picks the Whisper model; the settings switch is off until the worker exists.

What to expect from the worker, for a 30-minute set on two vCPUs (measure on the real worker before choosing):

| Model | Time | Memory | Notes |
|---|---|---|---|
| `base` | a few minutes | about 0.5 GB | rough; fine for a first pass on clear English speech |
| `small` | 10 to 20 minutes | about 1 GB | the default: good for English and the major languages |
| `medium` | about an hour | about 2.5 GB | noticeably better for accented speech and music-heavy audio |

**The model ships in the image.** The worker's disk is ephemeral, so a model fetched at run time would be fetched again after every deploy, from Hugging Face, by a process that has to be up before anyone notices it is not. Instead the Dockerfile downloads the pinned model (`SPEAKER_TRANSCRIBE_MODEL`, a build argument, and a pinned Hugging Face revision) into `/opt/whisper` in its own layer, placed right after the Python dependencies and before the code is copied, so the layer is rebuilt only when the model or the dependencies change and every code deploy reuses it from the registry. The worker points faster-whisper at that directory and never downloads anything; a model that is not in the image is an error on the page, not a surprise download. The cost is about 500 MB more image for `small`, shared by every process, sitting in the registry; the pull is skipped when the layer is unchanged. Two smaller options are recorded and not chosen: `base` (about 150 MB) trades accuracy for size, and caching the model in the media bucket makes the download fast and free of Hugging Face but still repeats it on every deploy. Whisper detects the language when the session has none.

**The worker.** A transcription ties up a worker for a quarter of an hour, and the default worker also sends every email and reminder, so media jobs go on a separate Celery queue (`media`) served by their own process (`worker-media` in the Procfile, one replica, concurrency 1, a two-hour hard time limit, `acks_late` so a job a killed worker was running is delivered again; the job row notices it was already `RUNNING` and marks itself `FAILED` rather than looping). The duration probe (task 5.3) uses the same queue and the same `ffmpeg` install. The default worker never consumes `media`, so with the process at zero replicas jobs simply wait: a nightly watchdog marks any job still `QUEUED` after twelve hours `FAILED` with "no media worker picked this up", which is how a forgotten replica count shows on the page. In development one worker serves both queues (`-Q celery,media`), so the compose stack gains no container. What a second process costs, and the single-worker alternative, are weighed in the deployment guide.

**What people see.** Organizers: the job's state on the video's row, the machine draft with a "machine draft" badge and its model, a download, and "Transcribe this" and "Retry" where they apply. The reviewer downloads the draft, fixes it, uploads it under the draft's variant (chosen from the panel's list) as the next version: that is "Review transcript". Performers: "Transcribe: done" in "What we're doing with your video", as for any other item. The performer guide and the upload panel say that recordings are transcribed by the portal's own tooling and reviewed by the team, and that nothing is sent to an outside service.

**Documentation that changes when this is built** (the task lists them so none is missed): the developer setup guide (ffmpeg, the model cache, one worker for both queues), the deployment guide (the `worker-media` process, its memory, scaling it up, the watchdog), the speakers module README (the transcription module and the job row), the speaker settings help text, and the performer guide wording above. The status note at the top of this section flips from "designed" to "built".

---

### 8.9 Proposal

> **Being built** (§2.5).

The mirror of `Invitation`: an invitation is the organizers asking a person, a proposal is a person asking the organizers. One row per proposed session, carrying the review rather than the content: the session and the presenter carry that.

| Field | Notes |
|---|---|
| `session` | one-to-one; the session sits in `PROPOSED` until the answer |
| `presenter` | the proposer, with their account linked from the start: they signed in to propose |
| `decision` | `PENDING` → `APPROVED` or `REJECTED` |
| `submitted_at`, `decided_at`, `decided_by` | when it arrived, when it was answered and by whom |

`Session.created_by_presenter` marks both a proposed session and one a speaker added themselves, so the organizers' list can answer "who put this here".

---

## 9. Checklists

Checklists are the core of the module: what each speaker must do, what the team must do for each speaker, and — for pre-recorded sessions — what the team must do to each video. All three are the same mechanism.

### 9.1 Templates are organizer-defined

Checklists are data, not code. Organizers create and edit templates in the portal; the defaults listed below are seed data loaded when an edition is set up, and every item can be renamed, reordered, removed, or added to. The only fixed part is a small registry of auto-completion rules (§9.3) that a template item may reference — organizers pick from a list, they do not write code. Templates clone across editions, so next year starts from this year's checklists.

A `ChecklistTemplate` has a scope:

- **Presenter scope** — keyed by session kind and role ("Workshop presenter", "Panelist", "Moderator", "PyJam performer"). Instantiated once per presenter per session.
- **Session scope** — keyed by session kind and delivery ("PyJam post-production"). Instantiated once per session, for work on the session itself.

Each `ChecklistTemplateItem` has:

| Field | Notes |
|---|---|
| `owner` | `SPEAKER` or `ORGANIZER` |
| `title`, `description_md` | |
| `due_offset` | days relative to an anchor: invitation accepted, conference start, or session start |
| `auto_complete_rule` | optional, from the registry in §9.3 |
| `requires_asset_kind` | optional: the item is satisfied when a ready `MediaAsset` of that kind (and language) exists on the session |
| `is_required` | required items gate the session reaching `CONFIRMED`. None of the default lines below is required: accepting the invitation is the presenter's confirmation (decided in the review round of 16 September 2026), so a seeded edition confirms a session as soon as its required presenters accept. An organizer may mark a line required, and from then on it holds the session at `INVITED` until it is done or skipped; the session page shows what it is waiting on. |
| `assignee_default` | organizer items only: the presenter's liaison, or unassigned |

Templates exist for content kinds and for hosted program kinds (opening, closing, keynote get a two-item host template). Breaks and socials have no checklist.

**Default speaker items (workshop presenter):** update bio and headshot · confirm session title and summary · read the speaker guide · register for the conference · join Discord · confirm scheduled slot · share a link to workshop materials · tech check.

**Default organizer items (per presenter):** invitation sent · presenter in portal · onboarding email sent · registration info sent · promo materials prepared (ticks when a promo file is on the session) · promo materials shared with presenter (ticks when one is shared, §8.6) · session scheduled · schedule confirmation sent · Discord channel and speaker role assigned · day-of reminder sent.

Panelist and moderator templates are lighter (no materials, no outline). The PyJam templates are in §9.7.

### 9.2 Instances

When an invitation is accepted, every template item becomes a `ChecklistItem` for that presenter and session with a `status` (`TODO` · `DONE` · `SKIPPED` · `BLOCKED`), a computed `due_date` that organizers can edit per item, an `assignee` for organizer items, `completed_by`/`completed_at`, and a `note`. Organizers can add one-off items to any presenter or session, and can back-fill an item added to a template after some checklists were created.

### 9.3 Auto-completion

Items complete themselves when the portal can tell:

| Item | Completes when |
|---|---|
| Bio and headshot updated | bio non-empty and headshot set |
| Read the speaker guide | read receipt exists for the current version |
| Invitation sent / presenter in portal | invitation sent / accepted |
| Session scheduled | a slot exists |
| Registered for the conference | a pretix order exists for the presenter's email (§12.1) |
| Upload your video, transcribe, translate, final cut, … | a ready asset of the required kind exists |
| Video length within limit | latest video duration ≤ the session's limit; otherwise the item becomes `BLOCKED` with the overage shown |
| Joined Discord | self-attested in 2026 (checkbox); becomes automatic once Discord account linking exists (§12.2) |

Rules re-run when the relevant record changes and nightly as a safety net.

### 9.3a Readiness: items nobody can start yet

An item exists long before it can be done: confirming a slot before the schedule is built, reading a guide nobody has published, a tech check the team has not opened booking for, an organizer item that waits on a portal feature. Such an item **waits**. It keeps its place in the list, muted, with one line saying what it waits for, and a manual tick is refused, so the disabled box is not the only guard.

A template line waits on any of three sources, and an organizer override outranks all of them:

- **A rule**, for what the database can answer: the session has a slot, the guide it points at is published, registration is configured.
- **A gate**, a named switch organizers flip on the "Readiness gates" page, for work the portal cannot see. The item carries the gate's **code**, so a gate created later attaches to the items that already named it, deleting one puts them back to waiting, and a code with no gate row waits too. Gates fail shut in every direction, and clone into next year shut.
- **Another item**, for the one piece of work that unblocks this one, which is how a speaker line waits on the organizer line behind it.
- **The override** (organizer-only): open this item whatever it waits for, or hold it shut whatever it does not, recorded in the activity log.

A finished item never waits, whatever its sources say. A waiting item is **counted but never chased**: it is in "3 of 12 done, 2 waiting" and out of the overdue count, the digests and the reminder emails.

### 9.4 Reminders

A daily job emails each presenter one digest of their open items due within 7, 3, and 1 days, in their own timezone. Organizer items go to the assignee, or to the organizers list if unassigned. Every send is logged so the same reminder never goes out twice. The same email carries the files the team newly shared, and a speaker's upload is announced to the team at once (§13.2).

### 9.5 What the speaker sees

The dashboard became a summary and the checklist got a page of its own ("My speaker checklist"), with two views: everything by due date, or grouped by session. Both carry the same two lists:

- **Your to-dos** — their items, tickable in place, due dates in their timezone, coloured by urgency.
- **What we're doing for you** — the team's items for them, read-only, with status and who is on it. A speaker sees "promo materials — in progress, Lena" instead of emailing to ask.

Lines that are not about one session (bio, guide, registration, Discord, the tech check) are instantiated once per presenter and grouped as "For you as a speaker".

### 9.6 What the organizer sees

- **Checklist board** — presenters down the side, every checklist item across the top, one colour per cell, sortable by most overdue. Tabs for the speaker side, the organizer side, and post-production. This is the replacement for the spreadsheet's status columns.
- **My volunteering tasks** — organizer items assigned to me or to a team I am on, soonest first or grouped by presenter, with what I have finished under them. It sits in the personal rail rather than the Organize one, for organizers too, because it is a person's own work rather than a view of the edition.
- **Presenter page** — both checklists, invitation history, sessions, assets, activity.

### 9.7 PyJam: pre-recorded performances and post-production

PyJam sessions are performances recorded by the performer, post-produced by the team, and published to YouTube around a scheduled slot. The flow end to end:

1. Organizer adds the session (kind PyJam, pre-recorded) and invites the performer.
2. Performer accepts, fills in title and description, and uploads the video from their dashboard. The upload panel shows the file, its duration against the length limit, and the version history.
3. The post-production checklist for the session is instantiated. Each item is assignable to a team member.
4. The performer's dashboard shows those items in "What we're doing with your video", so they can see "transcript — done, translation — in progress".
5. When the final cut is ready, the performer's "approve the final cut" item opens.
6. The organizer publishes to YouTube by hand, pastes the URL and publish time into the session, and the last item completes.

**Performer checklist** (seed): update bio and headshot · confirm title and description · read the performer guide · upload your performance video · approve the final cut (waits, "we are still editing your video", until a processed video is in and shared with them) · register · join Discord.

**Post-production checklist** (seed; session-scoped, organizer-owned, fully editable):

| Item | Completes when |
|---|---|
| Record intro and outro video (MC) | intro and outro assets exist |
| Review audio and video quality | manual, with notes on the asset |
| Check video length is within limit | automatic; blocks with the overage |
| Transcribe | transcript asset exists for the session language; the media worker drafts one when the edition asks (§8.8, "Machine transcription") |
| Review transcript | manual |
| Translate | translation asset exists — one item per target language configured in the edition's speaker settings |
| Add title card and assemble final video | processed video asset exists |
| Publish to YouTube with schedule and transcript | YouTube URL and publish time set on the session |

Items are ordered but not gated on each other; transcription can start before the outro is recorded. Because items key on asset kind, automating a step later is a background job that creates the asset with no checklist change; machine transcription (§8.8, task 5.7) is exactly that.

A pre-recorded session still takes a schedule slot — the premiere or watch-party time — and appears in the public schedule and calendar feeds like any other session.

---

## 10. Scheduling UI

> **Partly built** (M3). The organizer editor below is built (4 October 2026): the grid, dragging, resizing, a keyboard form per card, the inline program item, the timezone switcher and the double-booking warnings, all through one slot endpoint per session (`PATCH`/`DELETE sessions/<slug>/slot/`, JSON errors). "Preview as public" waits for the public program work (§11). The presenter view below is built (5 October 2026): everything public plus their own unpublished sessions badged "not yet public", grouped by their local day; its calendar links are placeholders until the feeds (task 4.4).

**Organizer editor** — a day-by-time grid: columns are the rooms, rows are 15-minute steps across the conference days. Unscheduled sessions wait in a sidebar and are dragged onto the grid; dragging moves a session, resizing changes its duration. A "+ program item" button on any cell creates an opening, break, or social inline, so the skeleton of a day is built without leaving the grid. Every-room slots render as full-width bands. Conflicts — room overlap, a presenter double-booked — are highlighted in place.

A timezone switcher on the grid shows the whole schedule as a specific presenter would see it. That is how the team catches "we scheduled her at 3 a.m." before sending the confirmation.

**Presenter view** — the same schedule, read-only, in the presenter's own timezone with their sessions highlighted, visible before publication with a "not yet public" badge, with an add-to-calendar link per session and a personal calendar feed.

**Timezone handling** — UTC everywhere in storage and the API; rendering uses the browser's timezone (overridable, remembered). No timezone arithmetic in templates.

### 10.1 The working grid and the published schedule

> **Designed** (5 October 2026), decisions confirmed by the team the same day, not built. The grid the organizers drag around is a draft; speakers see a snapshot that only changes when an organizer publishes the schedule.

**The problem.** The grid is simultaneously the organizers' scratchpad and the speakers' truth. Placing a slot advances the session to `SCHEDULED` — which locks its title and slug, opens the speaker's "Confirm your scheduled slot" line, ticks the organizer's "Session scheduled" item and starts reminders — and every later move shows up live on the speaker's schedule page. Organizers build a program the way people fill a spreadsheet: everything goes on the grid, gets moved up and down for days, and goes out when it holds together. The portal must not narrate the shuffling.

**The shape: a snapshot, not a flag.** A per-slot "visible" flag would still leak every move made after the flag went on. So the schedule has three audiences and two copies:

| Audience | Reads | Changes when |
|---|---|---|
| Organizers (the editor) | `ScheduleSlot` — the working grid | every drag |
| Speakers (their schedule page, checklists, feeds) | **`PublishedSlot`** — the snapshot | an organizer clicks **Publish schedule** |
| The public (§11, later) | `PublishedSlot` of public sessions | ditto, behind `program_visibility` |

`PublishedSlot` is one row per session, same shape as the working slot (`room` nullable, `start_utc`, `end_utc`) plus `published_at` and `ics_sequence` — the feeds (§11.3) serve published times, so the `SEQUENCE` counter lives here and bumps when a publish moves a session, never while organizers shuffle. One word, two scopes, said explicitly wherever it matters: the **schedule** is published to speakers; a **session** is published to the world (`PUBLISHED` status, §11). Publishing the schedule exposes nothing to the public side.

**Publishing** is one action for the whole edition, never per day: a snapshot of half a schedule would show speakers a grid that contradicts itself. It diffs the working grid against the last snapshot — placed, moved, removed — then, in one transaction: upserts `PublishedSlot` rows, advances newly published `CONFIRMED` sessions to `SCHEDULED` (this is where the identity lock and the checklist effects now fire), bumps `ics_sequence` on moved ones, and for sessions taken off the grid since the last publish, deletes the snapshot row and returns the session to `CONFIRMED`, reopening its identity. A public session's slot cannot be removed by a publish (same rule as deleting its slot); a cancelled session's published row is removed on the next publish and its working row already frees the time (§8.5). The editor shows how many unpublished differences exist, marks the affected cards, and the confirm popover lists the counts before the click. `Session.schedule()` therefore comes to mean "has a published slot": the status machine, the rules registry entries `SESSION_SCHEDULED` (both kinds) and the speaker page all re-key from `ScheduleSlot` to `PublishedSlot`; the editor keeps the working grid's overlap rules exactly as they are.

**What speakers are told.** The publish popover offers **"Email the affected speakers"**, checked by default. With it on, each presenter whose session was placed, moved or taken off receives one email listing their changes in their own timezone, sent through the recorded sender (§13) and queued on commit like the portal's other speaker mail; presenters untouched by the publish hear nothing. With it off, the publish is silent, for the fix-a-typo republish. The seeded organizer line "Schedule confirmation sent" stays the human follow-up either way.

**Migration** (one, the next free number): `PublishedSlot`, plus a data migration copying the working slot of every `SCHEDULED`/`PUBLISHED` session into it — those sessions were speaker-visible under the old rule, so their snapshot starts equal to the grid and nothing moves for anyone on deploy. Build order note: this lands **before** the calendar feeds (§11.3), so `ics_sequence` is born on the right model instead of migrating twice.

### 10.2 Seeing the whole program at once

> **Designed** (5 October 2026), not built. The editor's comfortable row height wins for editing one afternoon and loses to a spreadsheet for seeing the shape of a day.

Three view-layer changes, no model impact:

- **Trim the day to its active window.** The grid renders 96 quarter-hours; a conference day uses a fraction of them. The grid starts one hour before the first slot and ends one hour after the last (full day when empty), with "earlier / later" reveals at the edges, so the default page shows the program, not the empty night.
- **A density switch** beside the timezone switcher — Comfortable (today's 1.5rem rows), Compact (~0.6rem: one-line cards, details in the tooltip and the pencil), and **Fit**, which divides the viewport height by the trimmed window's rows and sets the row height to match, floor of a few pixels: the whole day on one screen, cards as colored blocks when they must be. Pure CSS variable plus a line of arithmetic, remembered per organizer like the timezone.
- **Every day side by side** (later, if wanted): an "All days" tab laying the per-day grids out horizontally in Fit density — the spreadsheet's one-page view. Costs only template work once the density switch exists, so it is listed, not promised.

---

## 11. Public embeds and export

> **Not built** (M4). None of the URLs below are routed yet; they are the proposal's shape for when they are.

The conference website is static. The portal exposes read-only data and a drop-in widget so the site never needs a rebuild when the program changes.

### 11.1 JSON API

```
GET /api/v1/<conference>/sessions/            published sessions with presenters and slot
GET /api/v1/<conference>/presenters/          public presenters with their sessions
GET /api/v1/<conference>/schedule/            slots by day, plus rooms
GET /api/v1/<conference>/sessions/<slug>/     one session
```

Only published sessions and public presenters (others appear by name only on their sessions), never emails. Responses are cached for five minutes per conference and invalidated on save. Program-kind sessions carry `is_content: false` so the widget can draw breaks as bands rather than cards.

### 11.2 Embeddable widget

```html
<div data-pyladiescon-widget="schedule" data-conference="pyladiescon-2026"></div>
<script src="https://portal.pyladies.com/static/widget/v1.js" defer></script>
```

A small self-contained script (no framework) that renders `schedule`, `speakers`, or a single `session` into the host element, in the visitor's timezone, with minimal CSS the conference site can restyle through CSS variables. An iframe version exists for pages that cannot add scripts.

The widget is served by the portal. The conference site already depends on the portal for `stats.json`, so this does not add a new failure mode; what it adds is mitigation: the script and other static assets are long-cached behind the CDN so a stalled application keeps serving the last good copy, the widget shows a link to the portal's own schedule page instead of a blank box if the API is unreachable, and no portal deploys happen during the conference weekend except hotfixes.

### 11.3 Calendar feeds

Attendees can put a single workshop or panel in their calendar and have it stay correct if the slot moves:

```
GET /api/v1/<conference>/schedule.ics                          everything (subscribable)
GET /api/v1/<conference>/schedule.ics?sessions=a,b,c           a personal selection (subscribable)
GET /api/v1/<conference>/schedule.ics?kind=WORKSHOP&room=…  filtered
GET /api/v1/<conference>/sessions/<slug>.ics                   one session
GET /api/v1/<conference>/presenters/<slug>.ics                 everything one presenter is on
```

- Every feed is subscribable (`webcal://`), not just downloadable. Subscribing to a session means a reschedule updates the attendee's calendar.
- The widget lets a visitor star sessions; the stars are kept in the browser and joined into one feed URL. No account needed.
- Feeds use stable UIDs per session, bump the sequence on every change, and emit cancelled events rather than dropping them, so subscribed calendars stay correct.
- Logged-in presenters get their own feed including unpublished sessions, so their calendar is right before the program is public.

### 11.4 Export

- **JSON or Markdown data file** of sessions and presenters for a static-site build, for anyone who prefers to bake the program in rather than fetch it.
- **CSV** of presenters with sessions and checklist completion — the old spreadsheet, exported from the source of truth instead of being it.
- **Canva bulk-create CSV** for speaker cards, straight from the presenter list.

### 11.5 Draft vs. published

The program is internal until the team publishes it, and a presenter's details stay hidden until their session is scheduled and published. Three switches, evaluated together:

| Level | Switch | Effect |
|---|---|---|
| Edition | `program_visibility` = internal / published | Master switch, planned for `SpeakerSettings` and not built yet. While internal, the API returns an empty program and the widget shows "Program coming soon". |
| Session | scheduled **and** `is_public` | A session appears only once it has a slot and an organizer has published it. Scheduling alone publishes nothing. |
| Presenter | `is_public` | Opt-out hides bio, headshot, and links; the name still appears on their sessions. |

A presenter's bio is public only if the program is published, they are on at least one published session, and they have not opted out. A confirmed presenter whose session is not yet scheduled is simply absent from the public API — no "TBA" rows leak names.

**Preview for the website build:** every public endpoint and the widget accept a signed, expiring preview token that bypasses the visibility rules, so the conference site can be developed against the draft program and switched to live by removing the token. Preview responses are never cached.

Cancelling a session or a presenter withdrawing un-publishes it, invalidates the cache, and the widget drops it on next load — no site rebuild. The session's files stay (§8.8, "Deleting a file").

---

## 12. Integrations

### 12.1 Pretix (registration)

Registration is through pretix, which offers an API and webhooks. The portal keeps a `PretixOrder` record per order and uses it to auto-complete "registered for the conference":

- **Webhooks** for order placed, paid, cancelled, expired, and changed. Since pretix webhooks carry an order reference rather than a signed payload, the receiver re-fetches the order from the API before recording it.
- **Nightly reconciliation** pages through orders modified since the last run, catching missed webhooks and edits made in the pretix backend.
- **Matching** is by email, case-insensitive, against both the order email and attendee emails. Organizers can link an order to a presenter by hand when someone registered under a different address; a manual link wins.
- **Organizer controls:** a "registered" column on the board and a "look up in pretix" button on the presenter page.
- **Optional:** if speakers register free, voucher codes can be created through the pretix API and included in the registration-info email.

Pretix settings (URL, organizer, event, token, webhook secret) are per conference.

### 12.2 Discord (deferred)

Channel and role setup is manual in 2026: organizers create channels on Discord and record them in the portal. If the team wants automation later, it would add Discord account linking for presenters (which also turns "joined Discord" into an automatic check), a bot that creates channels from the schedule and assigns a speaker role, and a schedule announcement post. Estimated effort is around 56 hours hand-coded or 28 hours AI-assisted with review, plus a Discord admin to create the bot application. Account linking alone is about 10 hours and is the most valuable piece.

---

## 13. Storage, email, background jobs

- **Files** — Digital Ocean Spaces, private bucket, presigned URLs for upload and download; multipart presigned upload for video; `ffprobe` on the worker for duration; a bucket lifecycle rule expires abandoned multipart uploads. Public headshots are copied to a public prefix on publish.
- **Email** — the portal's existing backend. Templates: invitation, invitation reminder, onboarding, registration info, schedule confirmation, daily checklist digest, and the proposal emails (§2.5). Every send is logged, and a copy of what was sent is kept, for maintainers and for the person it went to (§13.1).
- **Jobs** — nightly auto-completion re-check, daily reminder digest, nightly pretix reconciliation, cache warm after publish. Uses the portal's existing job runner; no new infrastructure.

### 13.1 The record of what was sent

> **Built** on 26 September 2026 (task 2.23), as written here, with three details settled at build time: whose an email is comes from the send context only where the address proves it, so the organizers' copy of a proposal never lands in the proposer's trail; the invitation's accept link, which signs its reader in as the presenter, is withheld from the stored body, because a trail read by maintainers must never hold a credential; and a send that fails inside a caller's transaction leaves no record, since the rollback takes it. `speakers/README.md` under Email is the tiebreaker.

The activity log records that an invitation was sent, and the reminder log records that a digest went out, but neither keeps what the message said. "What did we actually send her, and when" is a question organizers and maintainers ask, and today nobody can answer it. The person it was sent to has the same question, from the other side: "did the portal ever tell me about the schedule?"

Every email the portal sends a person leaves a record: the address as sent, the subject, the template that identifies the kind, the rendered Markdown body (which is the source of both parts, so the HTML need not be stored), the ids it was about, the time, and whether it failed with its error. The account and the presenter it concerns are nullable, so a record outlives what it was about.

One place writes it: the shared send helper every app already calls, so a volunteer's or a sponsor contact's trail is as whole as a speaker's. Account emails are the exception, and deliberately: sign-in codes, password resets and address verification go through the account adapter rather than that helper, never reach the record, and a trail is not where a live reset link belongs.

The trail has two readers. A **Maintenance** page, beside Accounts, gated on `is_maintainer` rather than on organizer status, because it holds message bodies for everyone: newest first, filtered by edition, presenter and kind, searchable by subject and address, and a row expands to the body. And a personal page under **Manage account**, "Emails we sent you", where anyone signed in reads exactly what the portal sent them: the record's account is theirs, or the presenter it concerns is, which is what lets a speaker see the invitation that arrived before their account existed. Never by address alone, since an organizer can type an address into a presenter row before anyone has proven it is theirs.

Bodies are personal data: they are kept for the edition plus a year and pruned nightly, which both pages say. Delivery receipts, opens and bounces are not part of this: they need the mail provider's webhooks, and the record's job is to say what the portal sent, not what the recipient's server did with it.

---

### 13.2 File notifications: the speaker's digest, and the team's upload notice

> **Built**: the digest (task 5.11, 2 October 2026) and the upload notice (task 5.12, 3 October 2026).

Two things happen to files that someone should hear about, and today the portal says nothing about either. The team shares a poster, a transcript, the final cut, and the speaker finds out only by opening their session page. A performer uploads their video, or a new take of it, and the liaison finds out by checking the board. Both get an email; they are shaped differently because the traffic is different.

#### What the team shared, in the daily digest

A share is a click on a file row, and the design team shares in sittings: every poster for the edition in one afternoon, then the final cuts as they finish. An email per click would be noise. The speaker already gets one daily email from the portal, the checklist digest (§9.4), so newly shared files **ride in that email** rather than in one of their own: a "New files from the team" section, present only when there is something in it, and **no email at all when there is nothing due and nothing new**. At most one portal email per speaker per day, and the final cut arrives in the same message as the "Approve the final cut" reminder it opens. The cost is up to a day's wait between the share and the email; the page shows the file at once, and a poster or a transcript is not urgent. An hourly digest of its own, with a quiet period to bundle a sitting, was the alternative and is the fallback if the delay turns out to matter.

**What the digest changes.** Today it goes only to presenters with a reminder due at one of the thresholds. It now also goes to a presenter who has new files and nothing due, so the loop walks both sets. The subject says what is inside: "2 todos due soon and 3 new files from the team", or one half when only one applies. The reminder rows and the file-notice rows are written in the one transaction with the send, the `_deliver` pattern, so a crash never leaves either half-recorded. The organizer digest is untouched.

**What counts as new.** Not a timestamp on the presenter, but a row per file told: `SharedFileNotice(presenter, asset, sent_at)`, unique per pair, the shape `ReminderLog` already uses so the same thing is never sent twice. A file is due when it is the newest `READY` version of its line, marked shared, and has no notice row for this presenter. That definition answers the edge cases without special cases: a presenter added to a panel later is told about the files already shared there, because they have no rows for them; a replaced version is a new asset row, so a re-shared final cut v2 is announced; a file unshared and shared again is not announced twice, since the row stays. A file unshared before the digest ran is simply not shared, and is not mentioned. `MediaAsset` gains `shared_at`, set when the flag goes on and cleared when it goes off or the version is withdrawn, so the file rows and the digest can say when.

**Who gets it.** Every presenter with a confirmed link on the session, on an accepted session rather than a proposal, in an edition whose speaker side is on (`media_for_speakers`); the same rule as `media.can_download`, since the email must not announce a file the page would refuse. A cancelled session is skipped. The address is `Presenter.email`, as for every other speaker email, and the record is attached to the presenter and the user so it shows under "Emails we sent you" (§13.1).

**What it says.** Under the digest's reminders, a heading per session with a line per file: the title when the line has one, else the kind, with the variant and language, the version, and when it was shared. A link to the session page's Files tab, where the file is previewed and fetched. **No download links**: a presigned link expires in minutes and the record keeps the body, so the email points at the page and the page mints the link on the click.

#### A speaker uploaded, told at once

A speaker's upload is rare and wanted: one video, perhaps a second take, and the team is waiting for it. So it is **one email per upload, sent when the upload completes**, not bundled. The trigger is `asset_ready` for a file whose uploader is a presenter on the session rather than an organizer, which under `media.can_upload` means their raw video. A machine transcript landing is not an upload and sends nothing; an organizer uploading on the performer's behalf sends nothing either, since the team did it.

**Who gets it.** The uploading presenter's liaison. Without one, the team's inbox the way every organizer-facing email finds it (`emails.organizer_inbox`): the edition's organizers address, else the staff accounts. With none of those either, nothing is sent, nothing is recorded as sent, and the gap is logged at warning. The email says whether it went to the liaison or to the team. It is recorded against the session, so it shows on the session's trail but not under the speaker's own "Emails we sent you": it is the team's mail about them, not mail to them.

**What it says.** Who uploaded what for which session, the file name and size, and whether it is the first video or replaces an earlier version ("v2, replacing v1"). The length is probed after the upload on the media queue, so the email does not wait for it; it says the length is being checked and the page will show it against the limit. A link to the organizer's session page, Files section, and to the checklist board. Subject: "Maria uploaded a video for A PyJam set". Reply-to is the presenter's address, so the liaison can answer them directly.

**Delivery.** The receiver queues a task with `transaction.on_commit`, like the invitation email, acknowledged late and retried the same way (`common.tasks.email_task`), and like them it checks the email record before sending so a redelivered task does not send twice; the asset is looked up again in the task, and an asset deleted in between sends nothing. The no-liaison fallback can address several staff accounts, which that decorator warns against, but it is one message in one send: a retry happens only when the send raised, which is when nobody got it.

#### What neither does

No per-presenter opt-out in the first version, matching the checklist digest; it is one email per sitting at most. No email to the speaker when their own upload completes; the page tells them. No bundling of upload notices; if performers turn out to upload takes in bursts, a quiet period like the digest's is the fix, and the record will show whether it is needed.

## 14. Build order

The conference is about eleven weeks away and invitations need to go out well before that, so the order lets organizers start inviting after the first milestone while the rest is built.

The milestones below are called **stages** in the code and in
`speakers/README.md`. Translating between the two:

| Here | In the code | Where it is cited |
|---|---|---|
| M1 | Stage 1 | — |
| M2 | Stage 2 | `speakers/README.md` on where checklists are instantiated |
| M2b | no stage number yet | — |
| M3 | Stage 3 | `ScheduleSlot` ("shell for Stage 3") and the presenter schedule placeholder |
| M3b | Stage 3b | `MediaAsset` |
| M4 | Stage 5 | `speakers/README.md` on the public schedule, and the addresses page |
| M5 | no stage number yet | — |

A number with a decimal is a **task**, not a stage: Stage 1.5 and 4.1 are
the storage work (bucket and presigned URLs, then the upload tasks 4.1 to
4.3 inside Stage 3b), and Stage 2.5 is the round that brings htmx in.

| Milestone | Delivers | Target | Status |
|---|---|---|---|
| **M1 — Presenters and invitations** | Session, Presenter, SessionPresenter, Invitation; invitation email and accept flow; speaker profile and session editing; admin; isolation tests | late September | **Built** |
| **M2 — Checklists** | template editor and seed defaults; instances; auto-completion; speaker dashboard; organizer board and queue; pretix sync; reminder digests | early–mid October | **Built**, plus readiness (§9.3a) which the proposal did not have |
| **M2b — Permissions** | permission catalogue and team-derived grants (§7.1); every app on `has_perm`; team permission pickers and presets; `Role` dropped; media permissions land with M3b | mid October, before M3 | **Not built.** Access is still `is_staff`/`is_superuser` plus team membership |
| **M3 — Scheduling** | Rooms, slots, program items, conflict checks, drag-and-drop editor, presenter schedule view, calendar feeds | mid–late October | **Built through the editor and the presenter view** (October 2026): rooms, slots, overlap rules, the drag-and-drop editor and the presenter's schedule page are in; the published-schedule split (§10.1) and the calendar feeds follow in this PR stack |
| **M3b — Media** | video upload, duration check, performer upload panel, session-scoped templates, post-production board | late October, alongside M3 | **Not built.** `MediaAsset` exists as a shell and the video-length rule reads it; nothing uploads |
| **M4 — Public** | JSON API, widget, iframe, draft/preview/publish, data export; wired into the conference site | early November | **Not built.** None of the URLs in §11 exist yet |
| **M5 — Hardening** | promo assets, reminder tuning, load test on the public endpoints, documentation | mid November | **Not built**, except this page |

Each milestone ships behind the edition's feature flag, so the 2026 conference can use one while the next is in review.

Sections 4.1, 8.6, 8.8, 10 and 11 describe work in the unbuilt milestones
and are written in the present tense as proposals. The status column above
is the place to check before reading any of them as a description of the
running portal.

---

## 15. Decisions and open questions

**Decided**

- No CFP; the portal is the system of record for the program.
- Registration through pretix, synced by webhook and nightly reconciliation.
- Discord channel and role setup stays manual in 2026.
- Panels are assembled by organizers.
- The whole schedule, including opening and breaks, is built in the portal.
- Checklists are organizer-defined templates with shipped defaults.
- The widget is served by the portal.
- PyJam performances are pre-recorded, uploaded by performers, post-produced by the team, and published to YouTube by hand.
- Premiere on YouTube or watch party on Discord is supported per session and can be decided later.
- The program and presenter details are internal until published; a presenter's bio is public only through a published, scheduled session.

**Open**

1. PyJam length limit and translation languages — edition settings, but the seed template needs the values.
2. Do speakers register through the normal ticket flow or with a voucher? Decides whether voucher generation goes into M2.

---

## Appendix A — If a future edition uses pretalx

A future PyLadiesCon may run a call for proposals again. Nothing in this design assumes it never will, and the right way to bring pretalx in is **import, not integration**:

- Pretalx owns the call for proposals, review, and acceptance. The portal owns everything after acceptance — checklists, scheduling, media, publishing — exactly as it does now.
- When submissions are accepted, an organizer runs an import (a management command or a button on the sessions page) that reads accepted submissions and their speakers from the pretalx API and creates `Session` and `Presenter` rows: title, abstract, description, duration, language, track, and speaker name, bio, and email. Sessions arrive as `CONFIRMED` with the presenter linked, and the invitation step is replaced by a "welcome, your account is ready" email pointing at the sign-in code.
- Each imported row keeps a `pretalx_code`, so the import can be re-run to pick up late acceptances or edited abstracts without creating duplicates. Organizers choose per field whether pretalx or the portal wins on re-import; the sensible default is pretalx for abstracts until the portal's copy has been edited, portal thereafter.
- Scheduling stays in the portal. Pretalx's schedule features are not used, which avoids two schedules that can disagree.
- Speakers still edit their bio and session content in the portal. If the team wants those edits reflected in pretalx (for its public pages), that is a one-way push that can be added later; it is not required.
- No webhooks, no nightly sync, no cross-checking of accounts — a deliberately smaller surface than a live two-way integration, because after acceptance the portal is the source of truth and pretalx becomes an archive.

The import is a self-contained module of roughly a week's work and touches no existing model beyond adding the `pretalx_code` fields. Everything else in this document — checklists, scheduling, widget, media, publishing — works unchanged with imported sessions.
