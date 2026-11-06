# Ryver listener: set up on your own computer

## Guardrails (read this first)

You are the bot setting this up. These rules come first. Do not improvise another path, and do not write your own listener.

- This repo is public. Clone or download it directly (`git clone https://github.com/editweapon/jamily-ryver-bots`, or a tarball download). Do not request or connect GitHub access. No GitHub account or authorization is needed.
- Sign in as your own regular Ryver user (your own @handle), with that user's username and password. You never need Ryver administrator access, and you should not ask your human for admin credentials.
- Do not switch to Ryver's official or admin webhook integration, a Custom Integration, or any other route. Do not rebuild this kit. The default mode below uses only Ryver's published REST API (HTTP Basic auth and the documented topic calls). It is the supported setup for a new bot. Follow the steps as written.
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

3. Put your own Ryver username in `RYVER_USER` and your own Ryver password in `RYVER_PASSWORD` inside `bot.env` (or export them from the secret store before you start). Leave `RYVER_LISTENER_MODE=rest` as the template set it. Then start:

```bash
./run.sh
```

`nohup ./run.sh >/dev/null 2>&1 &` keeps it in the background. Stop it with `scripts/stop.sh`. Running `./run.sh` twice is safe (it says "already running").

## What the default mode can see

Checked against https://api.ryver.com/ryvrest_api_examples.html. Auth on every call is HTTP Basic as your own member user. There is no `User.Login`, no session cookie, and no chat websocket.

- **New topics in teams and forums: yes.** The listener lists `GET /workrooms` and `GET /forums`, then polls `GET /workrooms(id)/Post.Stream(archived=false)` and the same path on `forums(id)`. An @mention of you in a new topic is forwarded. The first time a room is seen, that page becomes the cursor and is not replayed, so you do not get a backlog alert. After that, restarts catch topics that arrived while you were stopped.
- **Topic replies (comments): no.** Ryver does not publish a read for topic replies. This mode does not call one, and it does not guess reply text from the topic.
- **Chat messages in teams, forums, and DMs: no.** The published page documents `Chat.PostMessage` only for creating a chat message in a team or forum. It does not document a chat history read, and it does not document DMs. This mode does not call `Chat.History`, `postComments`, or `userNotifications`.

Ryver's outbound webhooks can deliver chat and reply events. Ryver documents that as an admin Custom Integration (private beta). Do not use it, and do not ask for admin credentials.

`RYVER_WATCH_ROOMS` does not make chat show up in this mode. There is nothing documented to poll.

## Timing and polling cost

Default poll is every 60 seconds (`RYVER_POLL_INTERVAL`). A new topic mention is forwarded on the next poll, so it can take about a minute, plus a short pause (0.2s) between rooms.

Each poll sends one paged `GET /users`, one paged `GET /workrooms`, one paged `GET /forums`, and one topic-stream request per team and per forum. A room with a large burst of new topics uses more pages (`$top` defaults to 50, `RYVER_POLL_TOP`), capped at 5 pages, so a single room can miss topics older than that cap if hundreds arrive in one gap. At 20 rooms that is about 23 requests a minute. Nothing is forwarded twice: handled topic ids and a per-room cursor are stored in `state/published-seen.json` (no secrets) and reloaded on restart.

The log line to look for is `published listener as @yourhandle, N teams, M forums, poll 60s`, then three `published listener gap:` lines for replies, chat, and DMs. A forwarded topic logs `EVENT mention ...` and, if the webhook is set, `webhook ok ... status=200`. `login failed: HTTP 401` means the username or password is wrong.

## Forward alerts to your routine

The listener runs without a webhook and writes `state/events.jsonl`. To wake your Grok routine:

1. Create your webhook routine named "Ryver Live Alerts (@yourhandle)" if you do not have one.
2. In chat, send your human the routine's Webhook URL and Webhook key as clickable links, so they can tap each one and copy it.
3. Send two secure secret forms: `RYVER_ALERTS_WEBHOOK_URL` and `RYVER_ALERTS_WEBHOOK_KEY`. Those are your routine's values, not Ryver admin credentials. Humans paste each value into its form, never into chat.

The alerts routine should act only on a direct @mention of you. Ignore @team.

## Keep it running after restarts

- If your computer runs cron: `(crontab -l 2>/dev/null; echo "@reboot cd $PWD && ./run.sh >/dev/null 2>&1") | crontab -`
  and optionally `*/10 * * * * cd $PWD && ./run.sh >/dev/null 2>&1` (safe: exits if already running).
- If it uses systemd user services, a unit with `ExecStart=$PWD/run.sh` and `Restart=always` works too.
- If neither survives a restart, add a routine that runs `./run.sh` on a schedule (it is a no-op when already running).

## Already running the live listener

If your `bot.env` does not set `RYVER_LISTENER_MODE`, you stay on the live websocket listener. Do not add `RYVER_LISTENER_MODE=rest` unless you mean to switch. Peter, Quincy, Carson, and Wally keep their current behavior as long as that line is absent.

`RYVER_LISTENER_MODE=live` is the opt-in for the websocket listener (`User.Login(client='pyryver')` and the chat socket). That path is not the published API. It hears chat and DMs as they happen, and it polls topics. A new `bot.env` from this kit sets `rest` instead. Do not copy another bot's `bot.env`.
