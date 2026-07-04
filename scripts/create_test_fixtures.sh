#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$ROOT/tests/fixtures/media"
SHORT="$MEDIA/short"
DVD="$MEDIA/video_ts/SAMPLE_DVD/VIDEO_TS"

mkdir -p "$SHORT" "$DVD"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install ffmpeg to generate media fixtures." >&2
  exit 1
fi

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc=size=320x180:rate=25 \
  -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -t 2 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac \
  "$SHORT/fixture-a.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc=size=320x180:rate=25 \
  -f lavfi -i sine=frequency=880:sample_rate=48000 \
  -t 3 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac \
  "$SHORT/fixture-b.mp4"

# Minimal synthetic VIDEO_TS-like structure for scanner tests. This is not a
# complete authored DVD; later patches use it to test file grouping heuristics.
printf 'synthetic ifo fixture\n' > "$DVD/VIDEO_TS.IFO"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc=size=352x288:rate=25 \
  -f lavfi -i sine=frequency=330:sample_rate=48000 \
  -t 2 -target pal-dvd "$DVD/VTS_01_1.VOB"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc=size=352x288:rate=25 \
  -f lavfi -i sine=frequency=550:sample_rate=48000 \
  -t 2 -target pal-dvd "$DVD/VTS_01_2.VOB"

cat > "$MEDIA/README.md" <<'TXT'
# PrivateTV media fixtures

This directory is used by tests and local development. Run:

    scripts/create_test_fixtures.sh

The generated videos are intentionally tiny and synthetic.
TXT
