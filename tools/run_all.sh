#!/bin/sh
# Record one full-track run per condition (same track, same seed), back to back.
# Needs the backend on 8001 and a built client: (cd web && npx vite build --base=/app/)
# usage: tools/run_all.sh [seconds=346] [track index=0]
cd "$(dirname "$0")/.."
SECS=${1:-346}
for cond in shove silent talk; do
  echo "== $cond"
  .venv/bin/python tools/headless_run.py "http://localhost:8001/app/?track=${2:-0}&condition=$cond&reset=1" "$SECS" \
    "JSON.stringify({chunks: window.__debug.chunks, fps: Math.round(window.__debug.fps), t: window.__debug.audio.time, stalls: window.__stalls})" "" \
    "0::(window.__debug.audio.source.el.pause(), 1)" "1.5::1"
done
