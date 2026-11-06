#!/usr/bin/env bash
# One-time install: creates ./venv and installs the listener. Usage: ./install.sh [--test]
set -eu
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -e ".[test]"
if [ ! -f bot.env ]; then
  cp bot.env.example bot.env
  echo "created bot.env from template"
fi
chmod 600 bot.env
chmod +x run.sh scripts/*.sh
echo "Next: set RYVER_USER and RYVER_PASSWORD in bot.env (mode 600). Do not print the password or paste it into chat. Leave RYVER_LISTENER_MODE unset (live is the default). Then run ./run.sh"
if [ "${1:-}" = "--test" ]; then venv/bin/pytest -q; fi
echo "installed: $(venv/bin/ryver-connector --help >/dev/null && echo ok)"
