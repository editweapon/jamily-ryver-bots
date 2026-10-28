#!/usr/bin/env bash
# Stop this kit's supervisor and listener.
cd "$(dirname "$0")/.."
P="${RYVER_STATE_DIR:-./state}/supervisor.pid"
[ -f "$P" ] && pkill -P "$(cat "$P")" ; [ -f "$P" ] && kill "$(cat "$P")" 2>/dev/null; rm -f "$P"; echo stopped
