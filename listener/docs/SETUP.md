# Setup guide (per bot owner)

## 1. Dedicated bot account
- Ask your Ryver admin to invite a **dedicated account for the bot** (e.g. `alex-cos`). Never use a
  person's personal credentials – the bot acts with the full permissions of whatever account it uses.
- Add the bot only to the teams/forums it needs. It can only see what that account can see.

## 2. Install
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install git+https://github.com/<you>/ryver-connector.git   # or pip install -e .
```

## 3. Environment variables
| Var | Required | Meaning |
|---|---|---|
| `RYVER_ORG` | yes | org slug (`acme` → acme.ryver.com) or full host/URL |
| `RYVER_USERNAME` / `RYVER_PASSWORD` | yes* | bot account login (basic auth → session) |
| `RYVER_TOKEN` | yes* | alternative: an existing session id |
| `RYVER_ALLOW_WRITES` | no | `1` enables posting/commenting/reacting. **Default off (read-only).** |
| `RYVER_DRY_RUN` | no | `1` = writes are logged/printed, never sent |
| `RYVER_ALERTS_WEBHOOK_URL` | no | listener POSTs events here as JSON |
| `RYVER_ALERTS_WEBHOOK_KEY` | no | sent as `Authorization: Bearer <key>` |
| `RYVER_WATCH_ROOMS` | no | comma list of room names/ids: all chat + topics there are forwarded |
| `RYVER_MENTION_NAMES` | no | extra aliases treated as @mentions of the bot (username is automatic) |
| `RYVER_GROUP_MENTIONS` | no | default `team,here,all`; set empty to ignore group mentions |
| `RYVER_POLL_INTERVAL` | no | poll seconds (default 60) |
| `RYVER_POLL_TOP` | no | topics per room per page in published mode (default 50) |
| `RYVER_LISTENER_MODE` | no | `rest` = published topic poll (set in a new `bot.env`). `live` = websocket. If unset, `live`, so existing installs stay on the websocket. |
| `RYVER_STATE_DIR` | no | logs/events dir for `scripts/supervise.sh` (default `./state`) |

\* one of username+password or token.

Keep these in an env file outside the repo (`chmod 600`), e.g. `~/.config/<bot>.env`, loaded with
`set -a; . file; set +a`. `.gitignore` excludes `.env*` / `*.env`.

## 4. Run
```bash
ryver-connector whoami                      # verify login (read-only)
ryver-connector teams / forums / users
ryver-connector history team 123 --top 10
ryver-connector listen --print              # foreground
ENV_FILE=~/.config/<bot>.env scripts/supervise.sh &   # auto-restart forever
ryver-connector --dry-run post team 123 "hi"          # preview a write
RYVER_ALLOW_WRITES=1 ryver-connector post dm 456 "approved reply"
```

## Security notes
- Dedicated bot account only; never personal credentials. Rotate the password if it leaks.
- Read-only by default; enable writes only for a specific, human-approved send.
- Recommended flow: listener → webhook → Grok Bot drafts → human approves → single write.
- The connector never marks messages read, never changes presence on purpose, never edits/deletes.
- Secrets are never logged; `RyverConfig` hides them from `repr`. Don't paste them into chats/tickets.
- Webhook key is a bearer secret; use HTTPS URLs only.

## Known limits
- New installs set `RYVER_LISTENER_MODE=rest`. That mode uses HTTP Basic as the bot's own member and only the published reads: `GET /users`, `GET /workrooms`, `GET /forums`, and `GET /workrooms(id)/Post.Stream(archived=false)` (forums use the same path). Topic replies, chat history, and DMs are not in the published examples (https://api.ryver.com/ryvrest_api_examples.html), so the rest mode does not call them. Do not replace it with an admin outbound webhook.
- The live websocket (`User.Login(client='pyryver')` + `{"type":"auth"}` message) is **undocumented**
  and may change without notice. It is opt-in (`RYVER_LISTENER_MODE=live`). If the variable is unset, the listener stays on this websocket path so existing bots do not change. The published REST API is the default only for a new `bot.env`.
- On the live websocket, chat @mentions and DMs arrive as they happen, in any room the account can see. Topics and topic replies are polled about every 60 seconds in those same rooms. `RYVER_WATCH_ROOMS` also forwards chat that does not @mention the bot.
- Live websocket chat that arrives while the process is down is not replayed. The published topic mode stores a cursor and picks up new topics after a restart, up to 5 pages per room.
- Room list is loaded at login; rooms the bot joins later are picked up on next reconnect.
- Some endpoints (`Chat.React`, `Chat.History`) follow observed web-client behaviour and may differ by
  Ryver version.

## Forwarding @mentions of other bots (multi-bot routing)

The listener can also forward any event that directly @mentions *another* bot's handle to that bot's own webhook.

- Config file: `$RYVER_BOTS_FILE`, or `./bots.json` in the repo root if it exists. If neither exists, the feature is off.
  The file holds **no secrets**: `{"<handle>": {"webhook_url": "https://...", "webhook_key_env": "RYVER_BOT_<HANDLE>_WEBHOOK_KEY"}}`.
  The bearer key is read from the env var it names when the listener starts. A bot whose key var is unset is skipped and a warning is logged (the warning names the var, never its value).
  `chmod 600 bots.json` (the listener warns if the file is readable by group or others). See `bots.example.json`.
- Matching: whole-word, case-insensitive `@handle`. It does not match emails (`a@quincy.com`), longer handles (`@quincy_bot`, `@quincyx`), or `@team`/`@here`/`@all`.
  Messages written by that bot itself are skipped, so bots can't loop. Each (bot, message) pair is forwarded at most once.
- Scope: chat messages in any room the listener account can see, plus topics and topic comments in watched rooms (those are the only ones it polls).
  **Only rooms the listener account (@peter) belongs to are visible. The other bot's private DMs are never visible.**
- The body is the same event JSON, sent with `Authorization: Bearer <key>`. Mentions in rooms that are not watched use `kind: "bot_mention"`.
  Those events go **only** to the bot's webhook, not to the primary webhook or the JSONL file. Existing @peter behavior is unchanged.
- The config is read at startup, so restart the listener after you edit bots.json or the key env vars.
