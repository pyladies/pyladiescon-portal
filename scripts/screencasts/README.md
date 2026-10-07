# Screencasts

Records the walkthrough videos shown in the user guides:

| Video | Used in | Script |
|---|---|---|
| `speaker-propose-returning-volunteer.mp4` | `docs/user/speakers.md` | `rec-volunteer.js` |
| `speaker-invited.mp4` | `docs/user/speakers.md` | `rec-invited.js` |
| `organizer-invite-speakers.mp4` | `docs/user/organizer_invite_speakers.md` | `rec-organizer.js` |
| `speaker-upload-video.mp4` | `docs/user/speaker_files.md` | `rec-upload.js` |
| `speaker-replace-video.mp4` | `docs/user/speaker_files.md` | `rec-replace.js` |
| `speaker-files-from-the-team.mp4` | `docs/user/speaker_files.md` | `rec-team-files.js` |

The scripts drive the real portal in a headless browser (Playwright), against a
throwaway database with the sample data, and draw a cursor, click ripples and a
caption for each step into the video. Re-run them whenever a screen the guides
show changes. The MP4s are written to `scripts/screencasts/out/videos/`, which
git ignores. They are hosted on YouTube, not in this repository, so upload the
new take and update the embed in the guide (or use "Replace video" on YouTube
to keep the same address).

## What you need

- Node.js, `ffmpeg`, and the portal's Python environment (Django, psycopg2).
- The compose Postgres running (`docker compose up -d postgres`, published on
  port 5433) and maildev (`docker compose up -d maildev`, SMTP 1025, UI 1080).
  The invited and team takes open an email in maildev. Every take starts by
  emptying the maildev inbox (its `/email/all` endpoint), so point `MAILDEV_URL`
  at a maildev nothing else relies on.
- A Chromium for Playwright: either `npx playwright install chromium` in this
  folder, or point `PLAYWRIGHT_CHROME` at an existing Chrome for Testing binary.
- For the media takes, a bucket the browser can reach: the compose MinIO from
  `compose.override.yml` (`docker compose up -d minio`, published on port
  9000, bucket `speaker-media`) is the default. `ffprobe` measures the
  uploaded video's length and `ffmpeg` makes its thumbnail, in the server
  process, since the screencast settings run Celery tasks eagerly.

## Run it

From the repository root:

```
scripts/screencasts/run.sh --setup    # once: build and snapshot the database
scripts/screencasts/run.sh            # record every video
scripts/screencasts/run.sh volunteer  # or one take: organizer, invited, volunteer,
                                      # upload, replace, team
```

`--setup` creates the `pyladiescon_screencasts` database, migrates it, loads the
sample data on the screencast edition (2026) and runs `seed.py`, then snapshots
it. `seed.py` keeps one confirmed PyJam performer from the sample data, Maria
Performer, who signs in as `maria_performer`, with no video yet; the media
takes are hers. Every take starts by
restoring that snapshot and starting a server on port 8002, so a take that
uses up an invitation or a proposal can be re-run. Every take drops and
recreates that database, so the scripts read `SCREENCAST_DATABASE_URL`, never
the `DATABASE_URL` your development setup exports, and `db.py` refuses any
database whose name does not end in `_screencasts`. Nothing touches your
development database or the server on port 8000.

The `organizer` and `invited` takes always run together, in that order: the
organizer sends the invitation and the invited speaker accepts it. So do
`upload` and `replace`: the performer uploads her first video, then sends a
take that is over the limit, replaces it with a shorter one, and deletes her
video. The `team` take first runs `seed-team.py`, which puts the
sample files from `out/media` (three performance videos, a final cut, a poster
and a transcript, made by `ffmpeg` on first use) into the bucket as the
team's shared files and sends the day's digest, so the take can open the
"new files from the team" email in maildev. `shots-media` takes the
screenshots for the video-upload announcement post (`shoot-media.js`) on the
same data.

Settings, all optional environment variables:

| Variable | Default | |
|---|---|---|
| `PYTHON` | `python` | The interpreter with the portal's requirements. |
| `PORT` | `8002` | Port for the recording server. |
| `SCREENCAST_DATABASE_URL` | compose Postgres, `pyladiescon_screencasts` | The throwaway database. The name must end in `_screencasts`, or the scripts refuse to run. |
| `MAILDEV_URL` | `http://localhost:1080` | Where the emails arrive. |
| `PLAYWRIGHT_CHROME` | Playwright's own | Path to a Chrome binary. |
| `VIEWPORT_WIDTH`, `VIEWPORT_HEIGHT` | `1024`, `640` | See below. |
| `SAMPLE_PASSWORD` | `password123` | The sample data's password for every account. |
| `SCREENCAST_SESSION_TITLE` | `Duck Typing the Blues` | The performer's session in the media takes. |
| `SPEAKER_MEDIA_BUCKET` | `speaker-media` | The bucket the media takes upload to. |
| `AWS_S3_ENDPOINT_URL` | `http://localhost:9000` | Its endpoint, reachable from the browser. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | `minioadmin` | Its credentials. |

### Text too small in the video?

The videos are the size of the browser viewport. A smaller viewport makes the
text larger in the frame. Lower `VIEWPORT_WIDTH`, but keep it at 992 or more:
below that the portal switches to its mobile layout.

## Narrated takes

The three `rec-*.js` scripts follow a timeline: each step waits for `clock.at(t)`,
the second at which the narrator says it, and typing is paced to finish by a set
time. The times come from the speakers' own recordings, so the video matches
the voice. The audio the current times were made for:

| Script | Narration | Length |
|---|---|---|
| `rec-volunteer.js` | proposing a session | 83.7 s |
| `rec-invited.js` | accepting an invitation | 86.9 s |
| `rec-organizer.js` | inviting a speaker | 79.2 s |
| `rec-upload.js` | uploading a performance video | 131.3 s |
| `rec-replace.js` | a take over the limit, a shorter one, and deleting the video | 121.4 s |
| `rec-team-files.js` | files from the team, approving the final cut | 91.1 s |

To re-time a script for new audio, transcribe the recording with word times
(faster-whisper works locally), then set each `clock.at(...)` to when that step
is spoken. A step that runs later than its time prints `late by ...`, which
tells you where to leave more room. Set `VOLUNTEER_END`, `INVITED_END`,
`ORGANIZER_END`, `UPLOAD_END`, `REPLACE_END` or `TEAM_END` (seconds) to make
a video slightly longer than its audio.

Then add the audio to the video, for example:

```
ffmpeg -i out/videos/speaker-invited.mp4 -i narration.m4a -map 0:v -map 1:a \
  -c:v copy -c:a aac out/videos/speaker-invited-narrated.mp4
```

## When a script fails

Each step waits for its element and stops with the selector it could not find.
Open the page in a browser, find what the label or field is called now, and
update that line. The scripts refer to the sample accounts (`admin_user`,
`vol_maya`) and the names in `generate_sample_data`, so a change there needs the
same edit here.

Run one take at a time while fixing (`run.sh volunteer`), and delete
`out/` freely: it holds the raw recordings, the headshot placeholder and the
server log, and is ignored by git.
