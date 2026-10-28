#!/usr/bin/env bash
# One-time install: creates ./venv and installs the listener. Usage: ./install.sh [--test]
set -eu
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -e ".[test]"
[ -f bot.env ] || { cp bot.env.example bot.env; chmod 600 bot.env; echo "created bot.env from template; edit it"; }
chmod +x run.sh scripts/*.sh
if [ "${1:-}" = "--test" ]; then venv/bin/pytest -q; fi
echo "installed: $(venv/bin/ryver-connector --help >/dev/null && echo ok)"
