# Email Delivery: Knowing an Email Was Sent (Architecture)

This document describes how the portal tells a maintainer, in one place,
whether each email it was asked to send actually went out, what happens to
the ones that did not, and how a silent worker stops being silent. It is the
reference for any work that touches `common/send_emails.py`,
`common/tasks.py`, the Celery settings in `portal/settings.py`, the
`EmailDispatch` model, or the Maintenance > Delivery page.

Status: partly built. Sections marked *build* say what lands and where.
**Built on 1 October 2026:** the audit and retrigger page (Maintenance >
Invitations, `speakers/delivery.py`), the `LOGGING` setting, and log lines
for a queued task, the invitation task and a retrigger. Everything else
below is still design.

## Why

On 1 October 2026 the presenter page showed an invitation as sent, and
Maintenance > Emails had no record of it. Other invitations to the same
session, sent in the same minute, did have records, and at least four more
speakers, invited at different times, were in the same state. Nothing in
Sentry. A synchronous run of the same task for one of them succeeded, so the
invitation, the address, the template and the mail provider were all fine.
The email was lost between the web request and the worker.

Three properties of the current code made that possible and invisible:

1. **"Sent" is a claim made by the web process.** `Invitation.issue_token()`
   stamps `sent_at` when the task is queued. The presenter page, the session
   page and the checklist rules all read that stamp. Nothing writes anything
   when the worker actually delivers, so the stamp and the email can
   disagree for good.
2. **A lost task raises nothing.** The email tasks are acknowledged when the
   worker receives them (Celery's default). If the worker is killed or
   restarted while it holds one, the task is gone: no exception, no
   `FAILED` record, no Sentry event. `enqueue()` also swallows a broker
   outage, logging it and letting the request succeed.
3. **The only record is written by the thing that failed.** `SentEmail` is
   written by the worker, after rendering and delivery. Absence of a row is
   the only evidence, and nobody looks for an absence.

The fix is not a better error handler. It is to record the *intent* to send
in the same transaction that makes the claim, to have the worker close that
record, and to have something that notices when it is not closed.

## Goals

- Every email the portal is asked to send has a row saying what was asked,
  for whom, and where it stands: queued, sending, sent, failed or stalled.
- The presenter page says "Queued", "Sent" or "Failed", from that row,
  never from the web process's own stamp.
- A task lost in a restart is delivered again without anyone acting.
- A task that cannot be delivered, or that stays unfinished, is visible on
  one page and in Sentry, with enough in the log line to find the worker's
  side of the story.
- A maintainer can resend from that page, singly or in bulk.
- Silence is detectable: if a worker stops consuming, or stops reporting to
  Sentry, something says so.

## Non-goals

- Delivery receipts, opens and bounces. "Sent" means the mail provider
  accepted the message. What the recipient's server did with it needs the
  provider's webhooks, which is a separate piece of work (see Later).
- Replaying a stored body. The record holds the rendered Markdown with the
  sign-in link withheld (design `speaker-portal.md` section 13.1), so a
  resend always runs the original action again and builds a fresh email.
- Changing who receives what. No recipient is ever added, and a resend goes
  to the address on the dispatch, not a new one.
- Account emails (sign-in codes, password reset). They go through the
  account adapter and stay out of every record, as today.

## The model

### `EmailDispatch` (common app)

One row per request to send an email. It holds no message body, so it is not
personal data in the way `SentEmail` is, and it is not shown to recipients.

| Field | Meaning |
|---|---|
| `id` | UUID. Also the Celery `task_id`, so a worker log line carries it. |
| `kind` | The template or task family, e.g. `speakers/invitation`. |
| `task` | Dotted task name, so the reconciler can enqueue it again. |
| `args` | JSON list of the task's arguments (ids only). |
| `to` | The address it was addressed to when requested. |
| `conference`, `presenter`, `invitation` | Nullable links, for filtering and for the presenter page. `SET_NULL`. |
| `requested_by`, `requested_at` | Who asked, and when. |
| `status` | `QUEUED`, `SENDING`, `SENT`, `FAILED`, `STALLED`. |
| `attempts` | How many times a worker started it. |
| `started_at`, `finished_at` | Of the latest attempt. |
| `worker` | Celery hostname of the latest attempt. |
| `error` | Exception class and message, truncated, for `FAILED`. |
| `sent_email` | The `SentEmail` it produced, nullable. |

States and moves:

```
QUEUED --worker starts--> SENDING --delivered--> SENT
   |                         |
   |                         +--raises, retryable--> QUEUED (attempts + 1)
   |                         +--raises, permanent---> FAILED
   +--no worker within the stall window--> STALLED --reconciler re-queues--> QUEUED
                                            (after the attempt cap) --> FAILED
```

`SENT` and `FAILED` are final until a person resends, which creates a new
dispatch for the same target and leaves the old one as history.

### Why not put this on `SentEmail`

`SentEmail` answers "what did the portal tell this person", is read by the
recipient on their own page, and is deliberately written only when a send
happened. A `QUEUED` row with no body would appear in the speaker's trail
for an email they never got. Two tables, two questions: the dispatch is
what was asked, the sent email is what was sent, and `sent_email` joins
them.

## The request path

*build*

`enqueue_email(task, *args, kind, to, **links)` in `common/tasks.py`
replaces `enqueue()` for email tasks:

1. Inside the caller's transaction, create the `EmailDispatch` as `QUEUED`.
   If the action rolls back, so does the row. If it commits, the row exists
   whatever happens next.
2. On commit, send the task with `task_id=str(dispatch.id)`.
3. If sending raises (the broker is down), set `FAILED` with the error and
   log at error level. The row exists, so the page shows it, and the
   request still succeeds, as `enqueue()` does today.

`send_invitation` then stops treating `sent_at` as the delivery fact. It
keeps `sent_at` as "an organizer asked" (the token and its expiry still hang
off it), and the page reads the latest dispatch for the label:

| Dispatch | Label on the presenter page |
|---|---|
| `QUEUED` | Queued, not sent yet |
| `SENDING` | Sending |
| `SENT` | Sent, and when |
| `FAILED` | Not sent: the error, and a Resend button |
| `STALLED` | Not sent: no worker picked it up, and a Resend button |

Existing invitations have no dispatch. The page falls back to today's
wording for them, until the backfill below has run.

## The worker path

*build*

Email tasks share one decorator, `@email_task`, instead of a bare
`@shared_task`:

- `bind=True`, `acks_late=True`, `reject_on_worker_lost=True`. A task a
  killed worker was holding goes back on the queue. This is already how
  `build_export_zip_task` is declared; the email tasks were never given it.
- `autoretry_for` the transient errors (`smtplib.SMTPException` subclasses
  that are not recipient refusals, `OSError`), with backoff and jitter,
  `max_retries=5`. Permanent errors (`SMTPRecipientsRefused`, an address
  Django cannot encode) go straight to `FAILED`.
- The first thing the task does is load its dispatch and **return if it is
  already `SENT`**. With late acknowledgement a task can be delivered twice
  (a redelivery after the visibility timeout on Redis), and this is what
  keeps a presenter from getting two invitations. The dispatch is read with
  `select_for_update` so two workers cannot both pass the check.
- It then sets `SENDING`, `started_at`, `attempts + 1` and `worker`, runs the
  existing body, and on success sets `SENT`, `finished_at` and `sent_email`.
  The existing `SentEmail` write is unchanged.

Tasks that have no dispatch (queued by code that has not adopted
`enqueue_email`, or by a deploy mid-flight) still run: the decorator creates
the row at start if it is missing.

## The reconciler

*build*

A beat task, `reconcile_email_dispatches_task`, runs every five minutes on
the default queue, seeded as a periodic task by the migration like the
prune job.

- `QUEUED` for longer than `EMAIL_STALL_MINUTES` (default 10), or `SENDING`
  for longer than the task's time limit: set `STALLED`, log at warning, and
  enqueue it again under the same id with `attempts` unchanged.
- A dispatch that has been stalled and re-queued `EMAIL_STALL_RETRIES`
  times (default 2) becomes `FAILED` with "no worker completed this", and
  one error is logged for it. That log line is what reaches Sentry.
- It never touches `SENT` or `FAILED`.

This is the part that would have caught the 1 October invitations within
ten minutes: the task sat `QUEUED`, then `STALLED`, then was delivered by
the next pass.

## Logs

*Partly built.* `LOGGING` is in place (below), `enqueue` logs the id of the
task it queued, the invitation task logs when it starts, when it ends and
why it failed (never the address), and a retrigger logs who sent what again.
The dispatch transition lines in the shape below wait for `EmailDispatch`.

Until then the project had no `LOGGING` setting. Module loggers (`speakers.tasks`,
`common.tasks`) have no handler in the web process, so anything below
warning never reaches the platform's logs there. The Celery worker sets up
its own root handler, so its INFO lines do appear, which is why the worker
log is the place to look.

Add a minimal `LOGGING` to `portal/settings.py`: one console handler to
stdout, root at `WARNING`, and `portal.email`, `speakers`, `common` at
`INFO`. Every dispatch transition logs one line on the `portal.email`
logger in a fixed shape:

```
email.dispatch id=8b1f... kind=speakers/invitation status=SENT attempt=1 worker=celery@abc to_hash=ab12 target=invitation:482
```

The id is the Celery task id, so the worker's own `received` and
`succeeded` lines carry it too, and one search finds the whole story. The
address is logged as a short hash, not in full.

## Sentry

*build*

### What the code already does

`sentry_sdk.init` runs in `portal/settings.py`, behind `SENTRY_SDK_DSN`.
Every process imports those settings (the Celery app reads them), so web,
`worker`, `worker-media` and `worker-beat` initialise Sentry from the same
environment variable, and the SDK enables its Celery integration on its own
(it is in the SDK's auto-enabled list, and `sentry-sdk[django]` is
installed). A task that raises in a worker is reported without extra
configuration.

So the platform sharing one config is expected and not the problem. Two
other things explain "alerts only from web":

- **A lost task raises nothing.** There is no event to alert on. This is the
  1 October failure, and no Sentry setting changes it. The dispatch and the
  reconciler are what turn it into an error.
- **Alert rules can be scoped to web** (an issue alert filtered by
  transaction, URL or a tag only web events carry). That is configured in
  Sentry, not in the repo, and is the first thing to check there.

### What to add

- **Tag every event with its process.** At init, set `process` to `web`,
  `worker`, `worker-media` or `beat`, read from `sys.argv` (gunicorn, or
  `celery ... worker -Q media`). Events from a worker are then findable and
  alert rules can name them. Also set `environment` from an env var.
- **Report each worker start.** On Celery's `worker_ready`, log at INFO
  "worker ready: sentry=<on|off> queues=<...>" and send one Sentry message
  event tagged with the process. A worker that never says this is not
  reporting, and a worker that says it every few minutes is crash-looping
  (an out-of-memory kill looks exactly like this).
- **Use Sentry Crons for the silent case.** Set `monitor_beat_tasks=True` on
  `CeleryIntegration`, so a beat task that does not run, or does not finish,
  raises a missed check-in. The reconciler is the one that matters: if it
  stops running, nothing else here works. *Verify at build time* that this
  works with `django_celery_beat`'s database scheduler on SDK 2.43; if it
  does not, wrap the reconciler body with `sentry_sdk.monitor(...)` instead.
- **Log, do not swallow.** `enqueue_email` logs a failed send at error
  level. The default logging integration turns that into an event.

### A test that proves the path

A management command, `check_workers`, and a button on the Delivery page,
queue a task on each queue (`default`, `media`) that records a heartbeat and
can be told to raise on purpose. The heartbeat row (`WorkerHeartbeat`:
queue, hostname, seen_at, sentry enabled) is what the Delivery page shows.
Raising on purpose is how a maintainer confirms, once, that an error from
each worker really arrives in Sentry tagged with its process.

## Maintenance > Delivery

*build*

A page beside Accounts, Emails and Exports, gated on `is_maintainer` like
them (`MaintainerRequiredMixin`). Three parts:

1. **Workers.** One line per queue: last heartbeat, hostname, whether
   Sentry was on. Red if no heartbeat in ten minutes, with the text of what
   that usually means ("the worker is not running or not consuming this
   queue"). This is the same idea as `fail_stale_jobs`, which already tells
   a maintainer that `worker-media` is at zero replicas.
2. **Dispatches.** Newest first, filterable by status, kind, edition and
   presenter, searchable by address. Stalled and failed are on top by
   default. A row shows the error, attempts, worker, timestamps and a link
   to the sent email when there is one. The Celery task id is shown and
   copyable, because it is what to search the logs for.
3. **Resend.** A POST button per row. A bulk "resend all" is left out until
   the one-at-a-time page has been used for a while.

### What resend does

Resend never replays a stored body. It runs the original action again for
the target, through the same service function an organizer would use:

- Invitation: `send_invitation(invitation, actor=request.user)`. This
  issues a fresh token, so the earlier link stops working, and the page says
  so before the button is pressed. An accepted invitation is refused, as
  today.
- Other kinds: enqueue the same task again with the same arguments, as a
  new dispatch. These tasks are idempotent by construction (they read
  current state), so a second run is safe.

Every resend is recorded in the activity log with the maintainer as actor,
and the new dispatch links to the one it replaces. A resend goes to the
address on the target now, which is the same address an organizer's
resend uses.

The earlier design note on the Emails page ("there is no resend, which is a
different decision with its own consent questions") stands for that page,
which is the recipient-facing trail. Resend lives here, on the page about
the portal's own machinery, and resends only emails the portal itself
decided to send.

## Backfill

*build*

Dispatches only exist for sends after this ships. The speakers affected now
have none. A management command, `backfill_email_dispatches`, finds every
invitation with `sent_at` set and no `SentEmail` for it (matched on the
template, `context_digest.invitation` and a time at or after `sent_at`),
creates a `STALLED` dispatch for each, and with `--resend` queues them.
`--dry-run` is the default and prints the list. This is also the one-off
audit of how many speakers are affected, and it can run before anything else
here is built (see Rollout).

## Rollout

Each step is one pull request, and only step 3 has a migration.

1. **Find and fix the known cases.** *Built, as a page rather than a
   command:* Maintenance > Invitations lists every invitation of the active
   edition marked sent with no successful `SentEmail` for that send (a
   failed record is shown with its error), and sends them again one at a
   time, each with its own button (there is deliberately no bulk send: it
   emails a real person and ends their current link). It compares
   `Invitation.sent_at` with the records, so it needs no new table. It
   lists nothing sent before the `common` record table existed (the time
   migration `0001_sent_email` was applied, not the oldest surviving row,
   which the nightly prune moves forward and which a deployment whose worker
   was down at first does not have), skips invitations that were opened,
   accepted, declined or cancelled, and disables a row sent in the last five
   minutes, which may still be queued. The invitation's row is locked while
   it is sent, so two clicks cannot both send. A retrigger goes through `send_invitation` (a fresh link
   and expiry, as an organizer's resend does), writes an `invitation.retriggered`
   activity entry with the maintainer as actor, and logs a line. The page
   lists those entries. It cannot see an email the provider accepted
   before the process died and the row was saved, so sending again there is
   a duplicate, never a miss.
2. **Stop losing tasks.** `@email_task` with `acks_late`,
   `reject_on_worker_lost` and retries, `LOGGING`, the Sentry `process` tag
   and the `worker_ready` message, and a pinned `--concurrency` for
   `worker` in the `Procfile`. No migration. This alone ends the silent
   loss of a task a restarting worker held.
3. **Make it visible.** `EmailDispatch`, `enqueue_email`, the presenter-page
   labels, the reconciler, `WorkerHeartbeat`, the Delivery page and resend.
   One migration for the app, with the periodic task seeded in it.
4. **Adopt elsewhere.** Volunteer, sponsorship and the reminder digests move
   from `enqueue()` to `enqueue_email()`, one app per pull request. Until
   then they behave as today.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `EMAIL_STALL_MINUTES` | 10 | `QUEUED` this long counts as stalled. |
| `EMAIL_STALL_RETRIES` | 2 | Re-queues before a stalled dispatch is `FAILED`. |
| `EMAIL_DISPATCH_RETENTION_DAYS` | 90 | `SENT` dispatches older than this are pruned with the nightly job. `FAILED` ones are kept as long as the email records. |
| `WORKER_HEARTBEAT_MINUTES` | 5 | How often beat queues a heartbeat per queue. |

## Checking by hand today

For the maintainer who needs the answer before any of this exists:

- **Which invitations have no email?** In the Django shell, for each
  invitation with `sent_at` set, look for a `SentEmail` with
  `template="emails/speakers/invitation.md"`, `context_digest__invitation=<pk>`
  and `sent_at__gte=<invitation.sent_at>`. None means no email was recorded.
- **Why?** In the worker log around the invitation's `sent_at`, search for
  `Task speakers.tasks.send_invitation_email_task[`: a `received` with no
  `succeeded` means the worker died holding it; search for `WorkerLostError`
  or `Worker exited prematurely`, which are how a killed child process
  appears. No `received` at all means it never arrived: search the web log
  for `Failed to enqueue Celery task`.
- **Is the worker restarting?** The platform's events for the worker
  process: restarts and out-of-memory kills at the same times.
- **Which process's logs?** Cabotage runs each `Procfile` line as its own
  deployment (`docs/developer/deployment.md`, "Processes"), so `worker`,
  `worker-beat` and `worker-media` each have their own logs and replica
  count, separate from `web`. The web log holds only gunicorn's request and
  error lines, since the project sets no `LOGGING` and the app's own INFO
  messages are dropped there. Open the `worker` process, not `web`, and
  confirm it is scaled to at least one replica.
- **Is the worker too big for its container?** `celery worker` defaults to
  one child process per CPU it can see, and in a container that is often
  the node's core count, not the container's share. Each child imports
  Django, so a small memory limit is exceeded and the kernel kills a child
  holding a task. With the default early acknowledgement that task is lost.
  The `Procfile` should pin `--concurrency` for `worker`, as it already
  does for `worker-media`.

## Later

- The mail provider's webhooks (delivered, bounced, complained) feeding a
  `DELIVERED` / `BOUNCED` state on the dispatch, so "Sent" can become
  "Delivered".
- Telling the organizers, not only the maintainer, when a speaker's
  invitation could not be sent, on the session page where they are already
  working.
- Rate-limiting a bulk resend against the provider's sending limits.
