#!/usr/bin/env bash
# Keep `ryver-connector listen` running forever (restarts 5s after any exit).
# Usage: ENV_FILE=./bot.env scripts/supervise.sh [extra listen args]   (normally via ./run.sh)
set -u
cd "$(dirname "$0")/.."
if [ -n "${ENV_FILE:-}" ]; then set -a; . "$ENV_FILE"; set +a; fi
LOG_DIR="${RYVER_STATE_DIR:-./state}"; mkdir -p "$LOG_DIR"
if [ -f "$LOG_DIR/supervisor.pid" ] && kill -0 "$(cat "$LOG_DIR/supervisor.pid")" 2>/dev/null; then
  echo "already running (pid $(cat "$LOG_DIR/supervisor.pid"))" >&2; exit 0
fi
echo $$ > "$LOG_DIR/supervisor.pid"
BIN="${RYVER_CONNECTOR_BIN:-ryver-connector}"
while true; do
  "$BIN" listen --jsonl "$LOG_DIR/events.jsonl" "$@" >>"$LOG_DIR/listener.log" 2>&1
  echo "$(date -Is) listener exited $?, restarting in 5s" >> "$LOG_DIR/listener.log"
  sleep 5
done
