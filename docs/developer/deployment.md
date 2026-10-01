---
title: Deployment
description: Deployment Information for PyLadiesCon Portal
---

# Deployment

## Web app deployment

The web app is deployed to [cabotage](https://cabotage.us-east-2.psfhosted.computer/)
automatically whenever a PR is merged to `main`. Open pull requests are
**not** deployed; see [Pull request deployments](#pull-request-deployments)
for why.

### Release step and migrations

The `release` line in the `Procfile` runs before the new version starts
serving. It creates the cache table and runs `python manage.py migrate`
against the production database. Every migration file that reaches `main`
is therefore applied to production on the next deploy, without anyone
confirming it.

That gives migrations one rule: **a migration is frozen once it is merged.**

- While a pull request is open, its migration files may be regenerated,
  renamed or squashed freely. Nothing applies them except a developer's own
  database and the CI test run.
- After the pull request is merged, the migration is part of production's
  history. Never edit it in place, delete it or renumber it. Any further
  schema change is a new migration file, even a one-line fix.
- If production ever diverges from the migration files (a column missing,
  a migration recorded as applied that did something else), repair it with a
  new migration that checks before it acts, such as a `RunSQL` with
  `ADD COLUMN IF NOT EXISTS`. `speakers/migrations/0002_repair_invitation_sent_to.py`
  is an example.

Keep pull requests to one migration per app: squash the steps a branch
accumulated into a single regenerated file before asking for review, and
check it with `makemigrations --check` and a `migrate` on a fresh database.

### Pull request deployments

Cabotage can build and deploy every push of an open pull request as a
preview environment. This was **disabled on 2026-09-19** and should stay
disabled.

The preview environments shared the production database. Each push of a
pull request ran the same `release` step as a real deploy, so `migrate` was
applied to production from code that had not been reviewed or merged, and
that might never merge at all. Two things went wrong with that:

- A migration that was later changed on the branch (regenerated, squashed
  into another file, or dropped) had already been recorded as applied in
  production. Django then skipped the merged version, and production ended
  up with a schema that matched neither the branch nor `main`. This is how
  the `speakers_invitation.sent_to` column went missing and every session
  page returned a 500 until [#414](https://github.com/pyladies/pyladiescon-portal/pull/414)
  added it back.
- A pull request that is abandoned or rejected still leaves its tables and
  columns behind in production, with nothing in `main` describing them.

With pull request deployments off, only `main` touches production. Pull
requests are verified by the CI test run, which builds its own database
from the migration files, and by the Netlify preview for documentation.
If preview environments are wanted again, they need a database of their
own, separate from production, before they are re-enabled.

### Processes

Each line in the `Procfile` is a process that cabotage runs as its own
deployment: `web` serves requests, `worker` runs Celery tasks, and
`worker-beat` runs the Celery beat scheduler that dispatches the periodic
tasks stored in the database. `release` runs once per deploy, before the
others start.

Process names have to avoid cabotage's reserved names. `beat` is one of them,
which is why the scheduler is called `worker-beat`.

**A new or renamed process starts at zero replicas.** Cabotage does not scale
it automatically, and a deploy that adds or renames a Procfile entry reports
success without ever running the new process. After the deploy, open the
application in cabotage and scale the new process to the intended count,
typically 1. A renamed process is a new process from cabotage's point of
view: scale the new name up and the old name down.

`worker-beat` must run as exactly one replica. Two schedulers would dispatch
every periodic task twice.

If a scheduled task never fires, check the replica count before anything
else. In the Django admin, under *Periodic tasks*, a task whose *Last run at*
is empty has never been dispatched, which almost always means `worker-beat`
is not running.

### Database

The portal needs **PostgreSQL 15 or newer**. The speakers app declares unique
constraints with `nulls_distinct=False` (so a row with a NULL presenter
still counts as a duplicate of another). Django only emits that clause on
Postgres 15+; on an older server it warns with `models.W047` at check time
and creates the constraint without it, which silently allows the duplicates
the constraint exists to prevent. Production runs PostgreSQL 17 (17.2 as of
September 2026); local development and CI run `postgres:16` from
`compose.yml`, one major version behind, which is fine for the features the
portal uses. The image ships no `psql`, so `manage.py dbshell` does not work
in production; ask Django instead:

```
python manage.py shell -c "from django.db import connection; print(connection.pg_version)"
```

The number reads as major and minor: `170002` is 17.2.

### Adding a column during a rolling deploy

The release step runs `migrate` and only then serves the new release, so
there is a window, usually seconds, where the schema is new and the code is
old. A column added as NOT NULL breaks that window: Django backfills the
existing rows with a default and then **drops** it, so the column has no
database default, and a process from the previous release inserts a row
without it. Postgres refuses:

```
null value in column "default_team_name" of relation
"speakers_checklisttemplateitem" violates not-null constraint
```

It clears up on its own once the new release is serving, but it is 500s for
real people in the meantime, and it is avoidable. When adding a NOT NULL
column, give it a **database** default as well as a Python one:

```python
default_team_name = models.CharField(max_length=40, blank=True, db_default="")
```

`db_default` (Django 5) keeps the default in the schema, so the old code can
keep inserting until it is replaced. Keep the ordinary `default` as well:
with only a `db_default`, an unsaved instance holds a sentinel rather than
the value, and anything reading the attribute before the row is saved, a
`clean()` for instance, sees the sentinel.

`tests/speakers/test_deploy_window.py` walks the migration graph for every
column added to a table that already existed and fails if one is NOT NULL
with nothing behind it, so the rule cannot drift as columns are added. A
foreign key is the case where no default exists: add it nullable, backfill
it, and tighten it in a later release.

The same window applies to a column that is later removed: drop it from the
model first, deploy, then delete the column in a follow-up migration.

### Speaker media bucket

Speaker media (design §8.8) lives in its own **private** bucket, named by
`SPEAKER_MEDIA_BUCKET`, never the public-read one the image fields use. It
needs a lifecycle rule that aborts incomplete multipart uploads after 7
days (`AbortIncompleteMultipartUpload`): the portal's nightly "Expire
abandoned uploads" task reclaims what it knows about, and the rule reclaims
the rest. The bucket also needs a CORS rule allowing `PUT` from the portal's
origin with the `ETag` header exposed, since the browser uploads the parts
directly. Once bulk download exists (design §8.8, task 5.6) the same
rule needs `GET` as well, and a second lifecycle rule should expire the
`exports/` prefix after 7 days, since zip bundles are built there.

**Endpoint and region.** The media client reads `SPEAKER_MEDIA_ENDPOINT_URL`
and `SPEAKER_MEDIA_REGION`, each falling back to `AWS_S3_ENDPOINT_URL` and
`AWS_S3_REGION_NAME` when unset. Set them to the media Space's regional host
and region (`https://sfo3.digitaloceanspaces.com` and `sfo3`, say), not a
Space's own host: boto3 puts the bucket name in the path, so a host that
already names another Space signs every upload for the wrong Space, and the
browser's preflight fails with no `Access-Control-Allow-Origin`. A region
that is not the Space's gives a signature error. The image storage keeps
using the `AWS_*` variables unchanged. The access key must reach both Spaces.

**Read-only key for a post-production lead.** The bulk-download design
names one escape hatch that needs no portal code: a Spaces key with
read-only access to the media bucket, so one trusted person can pull an
edition with `rclone`. Create it under API, Spaces Keys, scoped to the
media bucket only with *Read* permission, and hand it over through the
password manager, never by email or chat. Revoke it when the edition's
post-production is done; nothing in the portal records what such a key
fetches.

```sh
rclone config create do-media s3 provider=DigitalOcean \
    endpoint=nyc3.digitaloceanspaces.com \
    access_key_id=<key> secret_access_key=<secret>
rclone sync do-media:pyladiescon-media/speaker-media/2026 ./pyladiescon-2026 \
    --progress --transfers 4
```

### The media worker

Media jobs run for minutes at a time: the duration probe (task 5.3, built)
measures every video that lands with `ffprobe`, and machine transcription
(task 5.7, designed) will run Whisper. They go on the `media` Celery queue
(`CELERY_TASK_ROUTES` in settings), served by the `worker-media` process
in the `Procfile` rather than the default `worker`, so a half-hour
transcription never holds up an invitation email.

- The image installs `ffmpeg`, which brings `ffprobe`.
- **`worker-media` is a new process, so it starts at zero replicas in
  cabotage** and has to be scaled to one by hand after the deploy that
  adds it (see "A new or renamed process" above); keep it at one replica,
  and it runs with concurrency 1. Until it is scaled up, every uploaded
  video shows "Length not checked yet" for good: the probe is queued and
  nobody is consuming the queue.
- A probe that fails records why on the asset ("Length not measured:
  ffprobe is not installed on the worker", for instance), which the file
  rows show, and logs an error; the asset itself stays usable.

When transcription lands:

- the Whisper model is part of the image (a Dockerfile layer downloads
  the pinned model into `/opt/whisper` at build time, before the code is
  copied, so a code-only deploy reuses the cached layer), and the worker
  never downloads at run time; changing `SPEAKER_TRANSCRIBE_MODEL` is an
  image rebuild, and a model missing from the image fails the job on the
  page rather than fetching it; give the process 2 GB of memory for
  `small`, more for `medium`;
- transcription runs entirely in this process; no audio leaves the
  portal's infrastructure, and there is no API key to manage.

**What a second worker process costs.** It is one more container on the
PSF-hosted cabotage cluster with its own memory reservation (the Whisper
model is what sets it), one more line to scale by hand after the deploy,
and one more thing that can be at zero replicas without anything failing
loudly: media tasks sit in Redis until a `worker-media` picks them up,
which is why the nightly watchdog marks a job queued for over twelve
hours as failed on the page. It shares the image, so `ffmpeg` and the
`faster-whisper` dependency are in every process's image whether or not
they use them (about 250 MB more image, plus about 500 MB for the
Whisper model layer). Everything else is unchanged:
`web`, `worker-beat` and `release` do not know it exists, and the default
`worker` keeps consuming only its own queue.

The alternative is one worker consuming both queues with two child
processes. It saves the container and the manual scale-up, but the whole
worker then needs the model's memory, a transcription and an email share
the same limits, and two slow transcriptions would hold every email until
one finishes. The separate process is the recommended shape; the single
worker is the fallback if the cluster cannot spare a container, and it is
a Procfile and settings change, not a code change.

### One-time configuration

Two things live outside the code and have to be set on a new environment:

**Site domain.** Emailed links (account verification, speaker invitations,
checklist reminders) are built from the domain in Django's sites framework,
which starts as `example.com`. After the first deploy, set it to the
portal's public hostname, either from the release shell:

```sh
python manage.py set_site_domain portal.example.org
```

or in the Django admin under **Sites**. Links are `https://` whenever
`DEBUG` is off.

**`FERNET_KEYS` environment variable.** The speaker portal stores the pretix
API token and webhook secret encrypted at rest and refuses to save them
without a key. Generate one once and keep it with the other deployment
secrets:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The variable is comma-separated so keys can be rotated: the first key
encrypts, every key decrypts. To roll a key, put the new one first, deploy,
re-save the stored secrets from the admin, then drop the old key. A single
`FERNET_KEY` is accepted too. A value stored under a key that is no longer
configured reads as unusable (pretix shows as not configured, and the app
logs it once) rather than breaking every page that loads the settings;
re-entering the secrets in the admin repairs it. Local development and the
test suite derive a key from `SECRET_KEY`, so neither needs the variable.

## Documentation deployment

The documentation is deployed to Netlify automatically whenever the PR is merged.

There is also a preview of the documentation for each PR, also generated by Netlify.

