#!/usr/bin/env bash
set -euo pipefail

OUT="tests/fixtures/sample_30s.mp4"
mkdir -p "$(dirname "$OUT")"
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=25 -f lavfi -i sine=frequency=1000:sample_rate=44100 -t 30 -shortest "$OUT"
