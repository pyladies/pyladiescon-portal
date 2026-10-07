#!/bin/bash
# Record the walkthrough videos used in docs/user/speakers.md,
# docs/user/organizer_invite_speakers.md and docs/user/speaker_files.md.
#
#   scripts/screencasts/run.sh --setup    build the throwaway database first
#   scripts/screencasts/run.sh            record every video
#   scripts/screencasts/run.sh organizer  record one: organizer, invited, volunteer,
#                                         upload, replace or team
#
# See scripts/screencasts/README.md. Settings come from the environment:
# PYTHON, PORT, SCREENCAST_DATABASE_URL, MAILDEV_URL, PLAYWRIGHT_CHROME,
# VIEWPORT_WIDTH, VIEWPORT_HEIGHT, SAMPLE_PASSWORD, and for the media takes
# SPEAKER_MEDIA_BUCKET, AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY (the compose MinIO by default).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/out"
VIDEOS="$OUT/videos"
MEDIA="$OUT/media"
PYTHON="${PYTHON:-python}"
PORT="${PORT:-8002}"

export SECRET_KEY="${SECRET_KEY:-screencasts}"
# Deliberately not DATABASE_URL: the compose setup exports that for the development
# database, and every take drops and recreates the database it points at. Only
# SCREENCAST_DATABASE_URL, whose name must end in _screencasts, can steer this.
export DATABASE_URL="${SCREENCAST_DATABASE_URL:-postgresql://pyladiescon:pyladiescon@localhost:5433/pyladiescon_screencasts}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export DEBUG=1
export DJANGO_SETTINGS_MODULE=screencast_settings
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_EMAIL_HOST="${DJANGO_EMAIL_HOST:-localhost}"
export DJANGO_EMAIL_PORT="${DJANGO_EMAIL_PORT:-1025}"
export DJANGO_DEFAULT_FROM_EMAIL="${DJANGO_DEFAULT_FROM_EMAIL:-PyLadiesCon <pyladiescon@example.com>}"
export BASE_URL="http://127.0.0.1:$PORT"
export SCREENCAST_DOMAIN="127.0.0.1:$PORT"
export MAILDEV_URL="${MAILDEV_URL:-http://localhost:1080}"
export HEADSHOT="$OUT/headshot.jpg"
# The media takes upload to a bucket: the compose MinIO (compose.override.yml)
# unless the environment names another. The browser PUTs the parts itself, so
# the endpoint must be one the browser can reach, not a container name.
export SPEAKER_MEDIA_BUCKET="${SPEAKER_MEDIA_BUCKET:-speaker-media}"
export AWS_S3_ENDPOINT_URL="${AWS_S3_ENDPOINT_URL:-http://localhost:9000}"
export AWS_S3_REGION_NAME="${AWS_S3_REGION_NAME:-us-east-1}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"
export SCREENCAST_MEDIA="$MEDIA"
# The performer's session in the media takes; seed.py renames the sample
# PyJam session to this, and the scripts find it by this title.
export SCREENCAST_SESSION_TITLE="${SCREENCAST_SESSION_TITLE:-Duck Typing the Blues}"

manage() { (cd "$ROOT" && "$PYTHON" manage.py "$@"); }
db() { "$PYTHON" "$HERE/db.py" "$@"; }

mkdir -p "$OUT" "$VIDEOS" "$MEDIA"
[ -d "$HERE/node_modules" ] || (cd "$HERE" && npm install)
[ -f "$HEADSHOT" ] || ffmpeg -v error -y -f lavfi -i "color=c=0xd6475f:s=480x480" -frames:v 1 "$HEADSHOT"

# Sample files for the media takes: three performance videos (a first take, a
# 12-minute one that is over the limit, and a shorter second take), the final
# cut, a square poster and a transcript. The
# videos are test patterns with a tone, big enough to show the upload progress.
sample_media() {
  [ -f "$MEDIA/performance.mp4" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=440:sample_rate=44100" -t 120 -c:v libx264 -preset veryfast -b:v 500k -pix_fmt yuv420p \
    -c:a aac -shortest "$MEDIA/performance.mp4"
  [ -f "$MEDIA/performance-take2.mp4" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=523:sample_rate=44100" -t 210 -c:v libx264 -preset veryfast -b:v 500k -pix_fmt yuv420p \
    -c:a aac -shortest "$MEDIA/performance-take2.mp4"
  # A 12-minute take, over the 10-minute limit, encoded small so it uploads quickly.
  [ -f "$MEDIA/performance-long.mp4" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=392:sample_rate=44100" -t 720 -c:v libx264 -preset ultrafast -b:v 150k -pix_fmt yuv420p \
    -c:a aac -b:a 64k -shortest "$MEDIA/performance-long.mp4"
  # The final cut is WebM (VP9), because the recording browser is Playwright's
  # Chromium, which has no H.264 decoder: an MP4 final cut would preview as a
  # player that never plays.
  [ -f "$MEDIA/final-cut.webm" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=330:sample_rate=44100" -t 150 -c:v libvpx-vp9 -b:v 600k -pix_fmt yuv420p \
    -c:a libopus -shortest "$MEDIA/final-cut.webm"
  [ -f "$MEDIA/poster-square.png" ] || ffmpeg -v error -y -f lavfi -i "color=c=0x2b1b4f:s=1080x1080" -frames:v 1 \
    -vf "drawbox=x=90:y=90:w=900:h=900:color=0xb57edc@1:t=12" "$MEDIA/poster-square.png"
  [ -f "$MEDIA/transcript-en.vtt" ] || cat > "$MEDIA/transcript-en.vtt" <<'VTT'
WEBVTT

00:00:01.000 --> 00:00:05.000
Hi, I'm Maria, and this is a set built from an empty file.

00:00:06.000 --> 00:00:11.000
Everything you hear is Python, running live.

00:00:12.000 --> 00:00:16.000
Let's start with a kick drum and a loop.
VTT
}

if [ "${1:-}" = "--setup" ]; then
  shift
  db create
  manage migrate -v0
  manage createcachetable
  manage generate_sample_data > /dev/null
  # The speaker sample data lands on the active edition, and the takes run on
  # the screencast year, so make that the active one first.
  manage shell -c "from portal.models import Conference; Conference.objects.update(is_active=False); Conference.objects.filter(year=${SCREENCAST_YEAR:-2026}).update(is_active=True)"
  manage generate_speaker_sample_data > /dev/null
  (cd "$ROOT" && "$PYTHON" manage.py shell < "$HERE/seed.py")
  db snapshot
fi

SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""; fi
}
trap stop_server EXIT

# Every take starts with an empty maildev inbox, so a take that opens an email
# shows that email alone in the sidebar, not what earlier runs (or the
# development server) left there.
clear_mail() { curl -s -o /dev/null -X DELETE "$MAILDEV_URL/email/all" || true; }

# Keep only the emails to one address; the team take opens the performer's
# digest, and the seed also sends the organizers theirs.
keep_mail_to() { # <address>
  curl -s "$MAILDEV_URL/email" | "$PYTHON" -c '
import json, sys, urllib.request
keep = sys.argv[1]
for mail in json.load(sys.stdin):
    if all(to.get("address") != keep for to in mail.get("to", [])):
        urllib.request.urlopen(urllib.request.Request(sys.argv[2] + "/email/" + mail["id"], method="DELETE"))
' "$1" "$MAILDEV_URL"
}

fresh_server() {
  stop_server
  clear_mail
  db restore
  # exec, so the pid is the server's own and stopping it stops the server, not a shell around it.
  (cd "$ROOT" && exec "$PYTHON" manage.py runserver "127.0.0.1:$PORT" --noreload > "$OUT/server.log" 2>&1) &
  SERVER_PID=$!
  until curl -s -o /dev/null "$BASE_URL/accounts/login/"; do sleep 1; done
}

seed_team() { (cd "$ROOT" && "$PYTHON" manage.py shell < "$HERE/seed-team.py"); keep_mail_to maria@example.com; }

encode() { # <recording dir> <name>
  ffmpeg -v error -y -i "$OUT/$1"/*.webm -c:v libx264 -crf 30 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -an "$VIDEOS/$2.mp4"
  echo "wrote scripts/screencasts/out/videos/$2.mp4"
}

record() {
  case "$1" in
    organizer)
      # The organizer take sends the invitation; the invited take consumes it,
      # so both run on the same fresh database, in this order.
      rm -rf "$OUT/organizer" "$OUT/invited"
      fresh_server
      node "$HERE/rec-organizer.js" "$OUT/organizer"
      node "$HERE/rec-invited.js" "$OUT/invited"
      encode organizer organizer-invite-speakers
      encode invited speaker-invited
      ;;
    invited) record organizer ;;
    volunteer)
      rm -rf "$OUT/volunteer"
      fresh_server
      node "$HERE/rec-volunteer.js" "$OUT/volunteer"
      encode volunteer speaker-propose-returning-volunteer
      ;;
    upload)
      # The performer uploads her first video; then, on the same database,
      # sends a take that is over the limit, replaces it with a shorter one,
      # and deletes her video.
      rm -rf "$OUT/upload" "$OUT/replace"
      sample_media
      fresh_server
      node "$HERE/rec-upload.js" "$OUT/upload"
      node "$HERE/rec-replace.js" "$OUT/replace"
      encode upload speaker-upload-video
      encode replace speaker-replace-video
      ;;
    replace) record upload ;;
    team)
      # The team's files are shared and the digest is sent before the take.
      rm -rf "$OUT/team"
      sample_media
      fresh_server
      seed_team
      node "$HERE/rec-team-files.js" "$OUT/team"
      encode team speaker-files-from-the-team
      ;;
    shots)
      # Screenshots for the announcement posts (see shoot-blog.js and shoot-media.js).
      sample_media
      fresh_server
      node "$HERE/shoot-blog.js"
      SHOTS_STAGE=before node "$HERE/shoot-media.js"
      seed_team
      node "$HERE/shoot-media.js"
      # A grey border, so a screenshot is clearly a picture of a page and not part of the post.
      for shot in "$OUT"/shots/*.png; do
        ffmpeg -v error -y -i "$shot" -vf "pad=iw+8:ih+8:4:4:color=0xaeb4bd" "$shot.bordered.png"
        mv "$shot.bordered.png" "$shot"
      done
      ;;
    shots-media)
      sample_media
      fresh_server
      SHOTS_STAGE=before node "$HERE/shoot-media.js"
      seed_team
      node "$HERE/shoot-media.js"
      for shot in "$OUT"/shots/*.png; do
        ffmpeg -v error -y -i "$shot" -vf "pad=iw+8:ih+8:4:4:color=0xaeb4bd" "$shot.bordered.png"
        mv "$shot.bordered.png" "$shot"
      done
      ;;
    script)
      # Debugging: run any script from this folder on a fresh database and server.
      sample_media
      fresh_server
      [ "${SEED_TEAM:-}" = "1" ] && seed_team
      node "$HERE/${SCRIPT:?set SCRIPT to a file in scripts/screencasts}"
      ;;
    *) echo "unknown take: $1" >&2; exit 1 ;;
  esac
}

if [ $# -eq 0 ]; then set -- organizer volunteer upload team; fi
for take in "$@"; do record "$take"; done
