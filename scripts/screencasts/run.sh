#!/bin/bash
# Record the walkthrough videos used in docs/user/speakers.md and
# docs/user/organizer_invite_speakers.md.
#
#   scripts/screencasts/run.sh --setup    build the throwaway database first
#   scripts/screencasts/run.sh            record all three videos
#   scripts/screencasts/run.sh organizer  record one: organizer, invited or volunteer
#
# See scripts/screencasts/README.md. Settings come from the environment:
# PYTHON, PORT, SCREENCAST_DATABASE_URL, MAILDEV_URL, PLAYWRIGHT_CHROME,
# VIEWPORT_WIDTH, VIEWPORT_HEIGHT, SAMPLE_PASSWORD.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/out"
VIDEOS="$ROOT/docs/assets/videos"
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

manage() { (cd "$ROOT" && "$PYTHON" manage.py "$@"); }
db() { "$PYTHON" "$HERE/db.py" "$@"; }

mkdir -p "$OUT" "$VIDEOS"
[ -d "$HERE/node_modules" ] || (cd "$HERE" && npm install)
[ -f "$HEADSHOT" ] || ffmpeg -v error -y -f lavfi -i "color=c=0xd6475f:s=480x480" -frames:v 1 "$HEADSHOT"

if [ "${1:-}" = "--setup" ]; then
  shift
  db create
  manage migrate -v0
  manage createcachetable
  manage generate_sample_data > /dev/null
  manage generate_speaker_sample_data > /dev/null
  (cd "$ROOT" && "$PYTHON" manage.py shell < "$HERE/seed.py")
  db snapshot
fi

SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""; fi
}
trap stop_server EXIT

fresh_server() {
  stop_server
  db restore
  (cd "$ROOT" && "$PYTHON" manage.py runserver "127.0.0.1:$PORT" --noreload > "$OUT/server.log" 2>&1) &
  SERVER_PID=$!
  until curl -s -o /dev/null "$BASE_URL/accounts/login/"; do sleep 1; done
}

encode() { # <recording dir> <name>
  ffmpeg -v error -y -i "$OUT/$1"/*.webm -c:v libx264 -crf 30 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -an "$VIDEOS/$2.mp4"
  echo "wrote docs/assets/videos/$2.mp4"
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
    shots)
      # Screenshots for the announcement post (see shoot-blog.js).
      fresh_server
      node "$HERE/shoot-blog.js"
      # A grey border, so a screenshot is clearly a picture of a page and not part of the post.
      for shot in "$OUT"/shots/*.png; do
        ffmpeg -v error -y -i "$shot" -vf "pad=iw+8:ih+8:4:4:color=0xaeb4bd" "$shot.bordered.png"
        mv "$shot.bordered.png" "$shot"
      done
      ;;
    script)
      # Debugging: run any script from this folder on a fresh database and server.
      fresh_server
      node "$HERE/${SCRIPT:?set SCRIPT to a file in scripts/screencasts}"
      ;;
    *) echo "unknown take: $1" >&2; exit 1 ;;
  esac
}

if [ $# -eq 0 ]; then set -- organizer volunteer; fi
for take in "$@"; do record "$take"; done
