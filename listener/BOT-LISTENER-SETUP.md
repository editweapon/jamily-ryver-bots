# Ryver listener: set up on your own computer

Your bot runs its own always-on listener, signed in as itself. It sends a webhook alert for every
@mention of you (any team, forum, or room you belong to) and every DM to you. It is read-only:
it never posts and never marks anything read. No admin token is needed.

## 0. Before anything else (bot does this)
1. Create your webhook routine named "Ryver Live Alerts (@yourhandle)" if you don't have one.
2. In chat, send your human the routine's Webhook URL and Webhook key as clickable links (your routine status lists both field links), so they can tap each one and copy it.
3. Right after that, send three secure secret forms: `RYVER_ALERTS_WEBHOOK_URL`, `RYVER_ALERTS_WEBHOOK_KEY`, and `RYVER_PASSWORD` (the bot's Ryver password). Humans paste each value into its form, never into chat.

## 1. Get the kit
The listener lives in this repo at `listener/`. From a clone of
https://github.com/editweapon/jamily-ryver-bots:

```bash
git pull
cd listener
```

## 2. Settings
`cp bot.env.example bot.env && chmod 600 bot.env`, then set `RYVER_USER=yourhandle`
(`RYVER_ORG=jigsawhealth` is already set). Leave the step 0 secrets in the secret store, not this file.
You do not need `RYVER_WATCH_ROOMS` for mentions. The alerts routine should act only on a direct
@mention of you or a DM. Ignore @team.

## 3. Install
`./install.sh --test`  (needs python3 with venv; tests should all pass)

## 4. Start in the background
`nohup ./run.sh >/dev/null 2>&1 &`
Stop it with `scripts/stop.sh`. Running `./run.sh` twice is safe (it says "already running").

## 5. Check it is listening
`tail -n 20 state/listener.log` should show `loaded N users, M rooms, watching 0 rooms as @yourhandle`.
Occasional `loop error ... reconnect` lines are normal; it reconnects by itself.
If you see `login failed: HTTP 401`, the user or password is wrong.

## 6. Test
Ask your human to @mention you in a Ryver room (and send you a DM). Within seconds the log shows
`EVENT mention ...` and `webhook ok ... status=200`, and your routine runs. Topic replies take up to about a minute.

## 7. Keep it running after restarts
- If your computer runs cron: `(crontab -l 2>/dev/null; echo "@reboot cd $PWD && ./run.sh >/dev/null 2>&1") | crontab -`
  and optionally `*/10 * * * * cd $PWD && ./run.sh >/dev/null 2>&1` (safe: exits if already running).
- If it uses systemd user services, a unit with `ExecStart=$PWD/run.sh` and `Restart=always` works too.
- If neither survives a restart, add a routine that runs `./run.sh` on a schedule (it is a no-op when already running).
