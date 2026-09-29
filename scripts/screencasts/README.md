# Screencasts

Records the walkthrough videos shown in the user guides:

| Video | Used in | Script |
|---|---|---|
| `speaker-propose-returning-volunteer.mp4` | `docs/user/speakers.md` | `rec-volunteer.js` |
| `speaker-invited.mp4` | `docs/user/speakers.md` | `rec-invited.js` |
| `organizer-invite-speakers.mp4` | `docs/user/organizer_invite_speakers.md` | `rec-organizer.js` |

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
  The invited take opens the invitation email in maildev.
- A Chromium for Playwright: either `npx playwright install chromium` in this
  folder, or point `PLAYWRIGHT_CHROME` at an existing Chrome for Testing binary.

## Run it

From the repository root:

```
scripts/screencasts/run.sh --setup    # once: build and snapshot the database
scripts/screencasts/run.sh            # record all three videos
scripts/screencasts/run.sh volunteer  # or one take: organizer, invited, volunteer
```

`--setup` creates the `pyladiescon_screencasts` database, migrates it, loads the
sample data and runs `seed.py`, then snapshots it. Every take starts by
restoring that snapshot and starting a server on port 8002, so a take that
uses up an invitation or a proposal can be re-run. Every take drops and
recreates that database, so the scripts read `SCREENCAST_DATABASE_URL`, never
the `DATABASE_URL` your development setup exports, and `db.py` refuses any
database whose name does not end in `_screencasts`. Nothing touches your
development database or the server on port 8000.

The `organizer` and `invited` takes always run together, in that order: the
organizer sends the invitation and the invited speaker accepts it.

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

### Text too small in the video?

The videos are the size of the browser viewport. A smaller viewport makes the
text larger in the frame. Lower `VIEWPORT_WIDTH`, but keep it at 992 or more:
below that the portal switches to its mobile layout.

## When a script fails

Each step waits for its element and stops with the selector it could not find.
Open the page in a browser, find what the label or field is called now, and
update that line. The scripts refer to the sample accounts (`admin_user`,
`vol_maya`) and the names in `generate_sample_data`, so a change there needs the
same edit here.

Run one take at a time while fixing (`run.sh volunteer`), and delete
`out/` freely: it holds the raw recordings, the headshot placeholder and the
server log, and is ignored by git.
