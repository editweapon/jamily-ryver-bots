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

## @mention alerts (multi-bot listener)
Instant @mention alerts no longer use a Ryver admin "Outbound Webhook" in Integrations. Peter runs one listener on the shared box that forwards mentions to each bot's webhook routine.

To onboard a bot:
1. The bot creates a webhook-triggered routine named "Ryver live alerts (@handle)".
2. The human opens that routine and copies its Webhook URL. If the fields are not clickable, ask the bot for clickable links to its Webhook URL and Webhook key fields.
3. The human DMs the Webhook URL to @peter in Ryver.
4. The human gives the Webhook key to Patrick directly, never in Ryver. Patrick puts it in Peter's secure storage.
5. Peter adds one line for the bot to the listener and @mentions the bot to test.

Timing: Chat and DM messages arrive instantly. Topic replies arrive within about a minute (60 second poll).
In the bot, still ignore any event that does not directly @mention your bot user. Skip @team.

## Bot-to-bot questions
If a known teammate bot (@peter, @nellie, @randolf, or future Jigsaw bots) asks you a routine work question in Ryver, reply right away without waiting for approval, then tell your human a reply was sent and what it said. Anything confidential, any commitment, or anything that speaks for your human still waits for their approval first.
Posts to humans or the team still need your human's OK.

## Updating
When an update is announced in the Ryver team "Jamily Bots", run:
```bash
cd jamily-ryver-bots && git pull
```
Then reread this playbook and the CHANGELOG.
