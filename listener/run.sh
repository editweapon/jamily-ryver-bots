#!/usr/bin/env bash
# Start the supervised, read-only Ryver listener for this bot.
# Reads ./bot.env (or ENV_FILE=path). Secrets may come from the environment instead.
set -eu
cd "$(dirname "$0")"
ENV_FILE="${ENV_FILE:-./bot.env}"
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
: "${RYVER_ORG:?RYVER_ORG not set}"
: "${RYVER_USER:=${RYVER_USERNAME:-}}"; export RYVER_USER
: "${RYVER_USER:?RYVER_USER not set}"
: "${RYVER_PASSWORD:?RYVER_PASSWORD not set}"
[ -n "${RYVER_ALERTS_WEBHOOK_URL:-}" ] || echo "warning: RYVER_ALERTS_WEBHOOK_URL not set; events only go to state/events.jsonl" >&2
export PATH="$PWD/venv/bin:$PATH"
unset ENV_FILE
exec scripts/supervise.sh "$@"
