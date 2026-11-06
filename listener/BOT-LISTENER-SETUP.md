# Ryver listener: set up on your own computer

## Is this approved? (read this first)

Yes. Run this kit as written. The default listener signs in as your own regular Ryver member (your username and password) and listens live for @mentions and DMs. That is the same pattern Ryver documents for its Hubot adapter: a normal member user, not an admin integration.

Ryver's own pages:

- [Creating a Ryver Bot](https://api.ryver.com/ryvbot_overview.html). Hubot uses a regular Ryver user and that user's credentials. BotKit uses a Custom Integration, which needs an organization admin and beta access from Ryver support.
- [Creating a Ryver Hubot](https://api.ryver.com/ryvbot_hubot_overview.html). Create a Ryver user for the bot, add it to the teams it should see, and connect the Hubot adapter.
- [hubot-ryver](https://github.com/ryverapp/hubot-ryver). The adapter is configured with `HUBOT_RYVER_USERNAME` and `HUBOT_RYVER_PASSWORD` for that member, plus the org host. It listens in direct messages, teams, and forums that user can access.
- [Ryver APIs overview](https://support.ryver.com/ryver-apis-overview/). Ryver's support page points developers at those docs.

Do not switch to BotKit, a Custom Integration, or an admin outbound webhook. Do not ask your human for Ryver administrator credentials. Do not write your own listener.

Guardrails:

- This repo is public. Clone or download it directly (`git clone https://github.com/editweapon/jamily-ryver-bots`, or a tarball download). Do not request or connect GitHub access. No GitHub account or authorization is needed.
- Sign in as your own regular Ryver user (your own @handle). You never need Ryver administrator access.
- Leave `RYVER_LISTENER_MODE` unset. That is the live listener, and it is the default for a new install. `RYVER_LISTENER_MODE=live` is the same thing. `RYVER_LISTENER_MODE=rest` is an opt-in fallback with the hard limits in the section below. Do not choose it unless your human asks for it.
- The only Ryver credentials to request from your human are your own Ryver username and password, through a secure form (the `bot.env` file this install creates, mode 600, or the platform secret store). Never ask for them in plain chat, and never print them.
- If something in the steps seems to need more access than this, stop and ask your human rather than improvising.

## Three steps

1. Clone the public repo and enter the kit. No GitHub login.

```bash
git clone https://github.com/editweapon/jamily-ryver-bots
cd jamily-ryver-bots/listener
```

2. Install. This creates a local venv, copies `bot.env` from the template if you do not already have one, and sets the file to mode 600. It does not print secrets.

```bash
./install.sh
```

3. Put your own Ryver username in `RYVER_USER` and your own Ryver password in `RYVER_PASSWORD` inside `bot.env` (or export them from the secret store before you start). Leave `RYVER_LISTENER_MODE` commented out. Then start:

```bash
./run.sh
```

`nohup ./run.sh >/dev/null 2>&1 &` keeps it in the background. Stop it with `scripts/stop.sh`. Running `./run.sh` twice is safe (it says "already running").

## What the default live listener does

It signs in as your member user and listens for:

- @mentions of you in chat, in any team or forum you belong to
- DMs to you
- new topics and topic replies (those are checked about every 60 seconds)

`tail -n 20 state/listener.log` should show `loaded N users, M rooms, watching 0 rooms as @yourhandle`. Occasional `loop error ... reconnect` lines are normal; it reconnects by itself. If you see `login failed: HTTP 401`, the username or password is wrong.

Ask your human to @mention you in a Ryver room and to send you a DM. Within seconds the log shows `EVENT mention ...` or `EVENT dm ...` and, when the webhook is set, `webhook ok ... status=200`. Topic replies can take about a minute.

You do not need `RYVER_WATCH_ROOMS` for mentions. That list only forwards every chat message from those rooms. The alerts routine should act only on a direct @mention of you or a DM. Ignore @team.

Chat that arrives while the process is stopped is not replayed. Topic polling catches topic activity that is still in the latest page after you start again.

If your `bot.env` does not set `RYVER_LISTENER_MODE`, you are on this live listener. Peter, Quincy, Carson, and Wally stay here as long as that line is absent. Do not copy another bot's `bot.env`.

## Opt-in fallback: RYVER_LISTENER_MODE=rest

Set this only when your human asks for the published-API poller. It uses HTTP Basic as your own member and only these reads: `GET /users`, `GET /workrooms`, `GET /forums`, and `GET /workrooms(id)/Post.Stream(archived=false)` (forums use the same path). Source: https://api.ryver.com/ryvrest_api_examples.html.

Hard limits:

- New topics only. An @mention in a new team or forum topic is forwarded.
- No topic replies.
- No chat messages.
- No DMs.
- Polls about every 60 seconds (`RYVER_POLL_INTERVAL`), so a new topic mention waits until the next poll.
- Dedupe is `state/published-seen.json` (topic ids and a per-room cursor, no secrets). The first time a room is seen, that page becomes the cursor and is not replayed. Restarts do not send the same topic twice. A burst larger than 5 pages of 50 topics in one room can leave older topics in that burst unseen.

The log line is `published listener as @yourhandle, N teams, M forums, poll 60s`, followed by `published listener gap:` lines for replies, chat, and DMs. `RYVER_WATCH_ROOMS` does not add chat in this mode.

## Forward alerts to your routine

The listener runs without a webhook and writes `state/events.jsonl`. To wake your Grok routine:

1. Create your webhook routine named "Ryver Live Alerts (@yourhandle)" if you do not have one.
2. In chat, send your human the routine's Webhook URL and Webhook key as clickable links, so they can tap each one and copy it.
3. Send two secure secret forms: `RYVER_ALERTS_WEBHOOK_URL` and `RYVER_ALERTS_WEBHOOK_KEY`. Those are your routine's values, not Ryver admin credentials. Humans paste each value into its form, never into chat.

## Keep it running after restarts

- If your computer runs cron: `(crontab -l 2>/dev/null; echo "@reboot cd $PWD && ./run.sh >/dev/null 2>&1") | crontab -`
  and optionally `*/10 * * * * cd $PWD && ./run.sh >/dev/null 2>&1` (safe: exits if already running).
- If it uses systemd user services, a unit with `ExecStart=$PWD/run.sh` and `Restart=always` works too.
- If neither survives a restart, add a routine that runs `./run.sh` on a schedule (it is a no-op when already running).
