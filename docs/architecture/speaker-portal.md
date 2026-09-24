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
- The schedule is built in the portal, assigned to Discord channels, and shown to everyone in their own timezone.
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

**In:** session and presenter management, invitations, speaker self-service profile and session editing, two-sided checklists with reminders, scheduling with Discord channel assignment, public schedule and speaker embeds with calendar feeds, promo asset storage, video upload and post-production tracking for pre-recorded sessions, CSV/JSON export, pretix registration sync.

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

A grid with Discord channels as columns and 15-minute steps as rows. Unscheduled sessions wait on the side and are dragged in; a "+ program item" button drops an opening or break straight onto the grid, spanning all channels. Conflicts — two sessions in one channel, a presenter double-booked — are highlighted where they happen.

The timezone switcher shows the grid as a specific presenter would see it, which is how "we scheduled her at 3 a.m." gets caught before the confirmation email.

### 3.5 Publishing

The program is internal until the team flips it to published. Each session is published individually and only once it is scheduled; a presenter's bio becomes public only through a published session. A preview link lets the conference website be built against the draft program.

## 4. PyJam performances

PyJam sessions are pre-recorded. The performer uploads the video; the team post-produces it and publishes to YouTube for a scheduled premiere or watch party.

### 4.1 The performer

> **Not built** (M3b). The upload panel and the post-production lists below are the proposal; today a performer sees their checklist and nothing uploads.

Same dashboard as any speaker, plus an upload panel: the video goes straight to storage in chunks and resumes if the connection drops, and the panel shows the duration against the length limit. The performer's second list is "what we're doing with your video", so they can watch it move through transcription, translation, and the final cut. When the final cut is ready, an "approve the final cut" item opens for them.

### 4.2 Post-production

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
 │     ├── ScheduleSlot ──── DiscordChannel            └── ChecklistItem (owner=SPEAKER)
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
| `kind` | A **`SessionType` row** per edition, not an enumeration: the list above became the seeded defaults (`WORKSHOP` · `PANEL` · `PYJAM` · `TALK` · `LIGHTNING`, and the program types `OPENING` · `CLOSING` · `KEYNOTE` · `ANNOUNCEMENT` · `BREAK` · `SOCIAL` · `OTHER`), and organizers add their own on the "Types and roles" page without a deploy. The row carries what the code used to switch on: `is_content`, the default duration and delivery, whether it spans all channels, and which `PresenterRole` rows it allows. |
| `delivery` | `LIVE` (default) or `PRE_RECORDED`. PyJam defaults to pre-recorded; any kind can be switched. Pre-recorded sessions get the media pipeline (§8.8) and a post-production checklist (§9.7). |
| `is_content` | read from the type row: a content type needs at least one presenter to be confirmed; a program type can be confirmed with none (a break) or with hosts (the opening) |
| `title` | required — the only required field |
| `summary_md`, `outline_md`, `prerequisites_md`, `audience_md`, `notes_md` | Markdown, all optional |
| `level`, `language`, `duration_minutes` | optional; duration defaults from kind (workshop 90, panel 60) |
| `video_length_limit_minutes`, `youtube_url`, `youtube_publish_at`, `premiere_location` | pre-recorded only. `premiere_location` is `DISCORD` (watch party in the slot's channel) or `YOUTUBE` (YouTube Premiere at the slot time), defaulting from the edition's speaker settings; it changes what the public card links to and nothing else, so the team can decide per session or late. |
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

**DiscordChannel** — `name`, `channel_id`, `url`, `kind` (`STAGE`, `VOICE`, `TEXT`, `FORUM`), `is_active`. Channels are created on Discord by hand and recorded here.

**ScheduleSlot** — one per session: `channel` (nullable — null means *all channels*, so the opening or a break spans the whole grid), `start_utc`, `end_utc`. `end_utc` defaults from the session duration.

Validation: no two slots overlap on one channel (an all-channel slot conflicts with everything in its window, except other program-kind bands); a presenter in two overlapping slots is flagged as a warning, not blocked — a moderator moving between rooms is legitimate.

All times are stored in UTC. `SpeakerSettings.conference_timezone` (one row per conference) is only the organizer's default display; the conference itself has no timezone.

### 8.6 PromoAsset

> **Not built** (M5). No such model exists yet.

Speaker cards, posters, and social images, attached to a session or a presenter, stored privately, downloadable by the speaker from their dashboard. Organizers upload them (the team's existing Canva workflow produces them; the presenter list exports directly to Canva's bulk-create CSV). Generating cards in the portal is a possible later addition.

### 8.7 Handbook

The speaker guide, versioned. Reading it records a `HandbookReadReceipt`; publishing a new version re-opens the "read the speaker guide" item for everyone who read the old one.

### 8.8 MediaAsset

> **Partly built** (M3b). The model exists and the video-length rule reads it; nothing uploads or probes a file yet.

For pre-recorded sessions, one row per file that moves through post-production:

| Field | Notes |
|---|---|
| `kind` | `RAW_VIDEO` (performer upload) · `INTRO` · `OUTRO` (MC recordings) · `PROCESSED_VIDEO` (final cut) · `TRANSCRIPT` · `TRANSLATION` · `TITLE_CARD` · `THUMBNAIL` · `OTHER` |
| `file` | Digital Ocean Spaces, private; presigned upload and download |
| `language` | for transcripts and translations, one row per language |
| `version` | increments on re-upload; old versions kept until deleted |
| `duration_seconds` | probed server-side after upload; drives the length-limit check |
| `status`, `notes_md` | `UPLOADING` · `READY` · `FAILED` · `SUPERSEDED`; reviewer notes ("audio clips at 4:10") |

Performance videos are routinely several gigabytes, so the browser uploads directly to object storage in chunks using presigned multipart URLs, with per-part retry and resume. The portal finalizes the upload and records the asset. Performers can upload raw video for their own sessions; organizers upload any kind.

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

**Default organizer items (per presenter):** invitation sent · presenter in portal · onboarding email sent · registration info sent · promo materials prepared · promo materials shared with presenter · session scheduled · schedule confirmation sent · Discord channel and speaker role assigned · day-of reminder sent.

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

A daily job emails each presenter one digest of their open items due within 7, 3, and 1 days, in their own timezone. Organizer items go to the assignee, or to the organizers list if unassigned. Every send is logged so the same reminder never goes out twice.

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

**Performer checklist** (seed): update bio and headshot · confirm title and description · read the performer guide · upload your performance video · approve the final cut · register · join Discord.

**Post-production checklist** (seed; session-scoped, organizer-owned, fully editable):

| Item | Completes when |
|---|---|
| Record intro and outro video (MC) | intro and outro assets exist |
| Review audio and video quality | manual, with notes on the asset |
| Check video length is within limit | automatic; blocks with the overage |
| Transcribe | transcript asset exists for the session language |
| Review transcript | manual |
| Translate | translation asset exists — one item per target language configured in the edition's speaker settings |
| Add title card and assemble final video | processed video asset exists |
| Publish to YouTube with schedule and transcript | YouTube URL and publish time set on the session |

Items are ordered but not gated on each other; transcription can start before the outro is recorded. Because items key on asset kind, automating a step later (say, machine transcription) is a background job that creates the asset — no checklist change.

A pre-recorded session still takes a schedule slot — the premiere or watch-party time — and appears in the public schedule and calendar feeds like any other session.

---

## 10. Scheduling UI

> **Not built** (M3). `ScheduleSlot` rows exist and the sample data writes them, but there is no editor and the presenter's schedule page is a placeholder.

**Organizer editor** — a day-by-time grid: columns are Discord channels, rows are 15-minute steps across the conference days. Unscheduled sessions wait in a sidebar and are dragged onto the grid; dragging moves a session, resizing changes its duration. A "+ program item" button on any cell creates an opening, break, or social inline, so the skeleton of a day is built without leaving the grid. All-channel slots render as full-width bands. Conflicts — channel overlap, a presenter double-booked — are highlighted in place.

A timezone switcher on the grid shows the whole schedule as a specific presenter would see it. That is how the team catches "we scheduled her at 3 a.m." before sending the confirmation.

**Presenter view** — the same schedule, read-only, in the presenter's own timezone with their sessions highlighted, visible before publication with a "not yet public" badge, with an add-to-calendar link per session and a personal calendar feed.

**Timezone handling** — UTC everywhere in storage and the API; rendering uses the browser's timezone (overridable, remembered). No timezone arithmetic in templates.

---

## 11. Public embeds and export

> **Not built** (M4). None of the URLs below are routed yet; they are the proposal's shape for when they are.

The conference website is static. The portal exposes read-only data and a drop-in widget so the site never needs a rebuild when the program changes.

### 11.1 JSON API

```
GET /api/v1/<conference>/sessions/            published sessions with presenters and slot
GET /api/v1/<conference>/presenters/          public presenters with their sessions
GET /api/v1/<conference>/schedule/            slots by day, plus channels
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
GET /api/v1/<conference>/schedule.ics?kind=WORKSHOP&channel=…  filtered
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

Cancelling a session or a presenter withdrawing un-publishes it, invalidates the cache, and the widget drops it on next load — no site rebuild.

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
- **Email** — the portal's existing backend. Templates: invitation, invitation reminder, onboarding, registration info, schedule confirmation, daily checklist digest, and the proposal emails (§2.5). Every send is logged, and a copy of what was sent is kept (§13.1).
- **Jobs** — nightly auto-completion re-check, daily reminder digest, nightly pretix reconciliation, cache warm after publish. Uses the portal's existing job runner; no new infrastructure.

### 13.1 The record of what was sent

> **Not built.** Decided on 24 September 2026; the stage after open proposals (§2.5).

The activity log records that an invitation was sent, and the reminder log records that a digest went out, but neither keeps what the message said. "What did we actually send her, and when" is a question organizers and maintainers ask, and today nobody can answer it.

Every email the portal sends a speaker leaves a record: the address as sent, the subject, the template that identifies the kind, the rendered Markdown body (which is the source of both parts, so the HTML need not be stored), the ids it was about, the time, and whether it failed with its error. Presenter and session are nullable, so a record outlives what it was about.

One place writes it. The speakers app already funnels every send through one helper, so the record is written there rather than in the shared mail code, and the other apps are untouched until they ask for the same thing.

The trail is a **Maintenance** page, beside Accounts, gated on `is_maintainer` rather than on organizer status, because it holds message bodies for everyone. Newest first, filtered by edition, presenter and kind, searchable by subject and address, and a row expands to the body.

Bodies are personal data: they are kept for the edition plus a year and pruned nightly, which the page says. Delivery receipts, opens and bounces are not part of this: they need the mail provider's webhooks, and the record's job is to say what the portal sent, not what the recipient's server did with it.

---

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
| **M3 — Scheduling** | Discord channels, slots, program items, conflict checks, drag-and-drop editor, presenter schedule view, calendar feeds | mid–late October | **Not built.** `ScheduleSlot` exists and is written by the sample data; there is no editor, and the presenter's schedule page is a placeholder |
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
