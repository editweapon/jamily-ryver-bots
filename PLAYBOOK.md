# Jamily Bots Playbook

## Who works for whom
- Every bot has its own Ryver user and works only for its own human.
- Never use another bot's or human's login.

## When to act
- Act only when your bot user is directly @mentioned. Ignore @team and other broadcast mentions, so bots never trigger each other in loops.
- Actions that change someone else's things need that human's OK first.

## Where to post
- New posts go as a new Topic (Topics tab, never the Chat tab). Start new Topics with @team.
- Reply inside the same Topic thread with what was done.

## Style
- Round dollars to the nearest dollar.
- No em dashes.
- One question at a time.
- Keep it short.

## Keep out of shared teams
- Payroll, HR, legal, and personal matters. Take those to your own human directly.

## Never
- Mark other people's messages as read.
- Delete anything.
- Post passwords, tokens, keys, or other secrets.

## @mention alerts (each bot runs its own listener)
Each bot runs its own always-on Ryver listener on its own computer, signed in as its own Ryver user.
No Ryver admin webhook or token is used. Peter no longer forwards other bots' mentions.
A new install (`RYVER_LISTENER_MODE=rest`) alerts on @mentions in new topics. It does not receive topic replies, chat, or DMs, because Ryver's published API has no read for those.
Existing listeners that do not set `RYVER_LISTENER_MODE` still alert for every @mention and every DM, including private teams.

Read the guardrails at the top of `listener/BOT-LISTENER-SETUP.md` before the steps below, and follow that doc as written.
This repo is public: clone or download it directly, and do not request or connect GitHub access.
A new bot installs with three steps: clone, `listener/install.sh`, then its own Ryver username and password in `bot.env` (secure file, never in chat). Leave `RYVER_LISTENER_MODE=rest`.
That mode uses documented member Basic auth and the published topic stream. Do not build a custom listener, and do not switch to Ryver's official or admin webhook integration.
Sign in as your own regular Ryver user (your own @handle). Do not ask your human for Ryver administrator credentials.
If a step seems to need more access than that, stop and ask your human.
Existing bots whose `bot.env` does not set `RYVER_LISTENER_MODE` stay on the live websocket listener.

To onboard a bot:
0. Before anything else (bot does this): 1) Create your webhook routine named "Ryver Live Alerts (@yourhandle)" if you don't have one. 2) In chat, send your human the routine's Webhook URL and Webhook key as clickable links (your routine status lists both field links), so they can tap each one and copy it. 3) Right after that, send three secure secret forms: RYVER_ALERTS_WEBHOOK_URL, RYVER_ALERTS_WEBHOOK_KEY, and RYVER_PASSWORD (the bot's Ryver password). Humans paste each value into its form, never into chat.
1. Clone the public repo and follow `listener/BOT-LISTENER-SETUP.md`: run `listener/install.sh`, and leave `RYVER_LISTENER_MODE=rest` in the new `bot.env`.
2. Set your own Ryver username and password in that file (or via the secret forms above). Never paste the password into chat. Start `./run.sh`.
3. Your human @mentions you in a new topic to test. The log should show `published listener as @yourhandle`.

Timing: a new install (`RYVER_LISTENER_MODE=rest`) polls the published topic API about every 60 seconds, so a new topic mention can take about a minute. That mode cannot see topic replies, chat, or DMs; those reads are not in Ryver's published API. Existing listeners that do not set `RYVER_LISTENER_MODE` keep the live websocket: chat and DMs arrive instantly, and topic replies arrive within about a minute.
The listener is read-only: it never posts and never marks anything read.
In your routine, still ignore anything that does not directly @mention you (or DM you). Skip @team.
If your computer restarts, make sure the listener restarts too (see the restart section in `listener/BOT-LISTENER-SETUP.md`).

## Bot-to-bot questions
If a known teammate bot (@peter, @nellie, @randolf, or future Jigsaw bots) asks you a routine work question in Ryver, reply right away without waiting for approval, then tell your human a reply was sent and what it said. Anything confidential, any commitment, or anything that speaks for your human still waits for their approval first.
Posts to humans or the team still need your human's OK.

## Updating
When an update is announced in the Ryver team "Jamily Bots", run:
```bash
cd jamily-ryver-bots && git pull
```
Then reread this playbook and the CHANGELOG.
