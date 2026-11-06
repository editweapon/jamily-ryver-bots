# ryver-connector

Connect AI bots (e.g. Grok Bot "chief of staff" agents) to [Ryver](https://ryver.com) team chat.

- **Read**: whoami, users, teams, forums, topics, topic comments, chat & DM history
- **Write** (off by default; `RYVER_ALLOW_WRITES=1`, `--dry-run` supported): chat message to forum/team/DM,
  create topic, comment on topic, react
- **Listen**: live websocket for DMs to the bot, @mentions (incl. @team/@here/@all), watched rooms;
  topic polling fallback; reconnect with exponential backoff; forwards JSON events to a callback
  and/or webhook (`Authorization: Bearer`)
- `scripts/supervise.sh` keeps the listener alive

```bash
pip install -e .
export RYVER_ORG=acme RYVER_USERNAME=acme-bot RYVER_PASSWORD=...   # use an env file in practice
ryver-connector whoami
ryver-connector listen --print
```

```python
from ryver_connector import RyverClient, RyverConfig
c = RyverClient(RyverConfig.from_env())
print(c.whoami()["username"])
```

See [docs/SETUP.md](docs/SETUP.md) and [examples/](examples/). License: MIT.

## Kit changes (per-bot listener)
Each bot runs this signed in as itself. Read "Is this approved?" at the top of BOT-LISTENER-SETUP.md first.
New installs leave `RYVER_LISTENER_MODE` unset: clone the public repo (do not connect GitHub), run `./install.sh`, and put your own Ryver username and password in `bot.env`. That default is the live listener, the same member-login pattern as Ryver's Hubot adapter. Do not build your own listener and do not use an admin Custom Integration.
`RYVER_LISTENER_MODE=rest` is an opt-in fallback: new topics only, no topic replies, no chat, no DMs, about a 60 second poll, dedupe in `state/published-seen.json`.
Bots that omit the variable stay on the live listener. Multi-bot forwarding (bots.json) is off unless RYVER_BOTS_FILE is set.
