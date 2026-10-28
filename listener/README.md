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
Each bot runs this signed in as itself; see BOT-LISTENER-SETUP.md. Mentions and DMs need no watch list;
topic/comment polling covers every room the bot can see. Multi-bot forwarding (bots.json) is off unless RYVER_BOTS_FILE is set.
