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
The default is the live listener: your own Ryver username and password, the same pattern as Ryver's Hubot adapter. It alerts you for every @mention of you and every DM to you, including private teams.
Read "Is this approved?" at the top of `listener/BOT-LISTENER-SETUP.md` before the steps below, and follow that doc as written.
This repo is public: clone or download it directly, and do not request or connect GitHub access.
A new bot installs in three steps: clone, `listener/install.sh`, then its own Ryver username and password in `bot.env` (mode 600, never in chat). Leave `RYVER_LISTENER_MODE` unset.
Do not build a custom listener, and do not switch to a Custom Integration or an admin webhook. Do not ask your human for Ryver administrator credentials.
`RYVER_LISTENER_MODE=rest` is an opt-in fallback: new topics only, no topic replies, no chat, no DMs, about a 60 second poll, dedupe in `state/published-seen.json`.
If a step seems to need more access than that, stop and ask your human.
Existing bots whose `bot.env` does not set `RYVER_LISTENER_MODE` stay on the live listener (Peter, Quincy, Carson, and Wally).

To onboard a bot:
0. Before anything else (bot does this): 1) Create your webhook routine named "Ryver Live Alerts (@yourhandle)" if you don't have one. 2) In chat, send your human the routine's Webhook URL and Webhook key as clickable links (your routine status lists both field links), so they can tap each one and copy it. 3) Right after that, send three secure secret forms: RYVER_ALERTS_WEBHOOK_URL, RYVER_ALERTS_WEBHOOK_KEY, and RYVER_PASSWORD (the bot's Ryver password). Humans paste each value into its form, never into chat.
1. Clone the public repo and follow `listener/BOT-LISTENER-SETUP.md`: run `listener/install.sh`, and leave `RYVER_LISTENER_MODE` unset.
2. Set your own Ryver username and password in that file (or via the secret forms above). Never paste the password into chat. Start `./run.sh`.
3. Your human @mentions you in a room (and sends a DM) to test. The log should show `loaded N users, M rooms, watching 0 rooms as @yourhandle`.

Timing on the default live listener: chat and DMs arrive within seconds. Topic replies arrive within about a minute (60 second poll). The opt-in `rest` mode is slower and narrower: new topic mentions only, about every 60 seconds, with no replies, chat, or DMs.
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
