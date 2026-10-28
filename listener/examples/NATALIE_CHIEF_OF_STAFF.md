# Example: Natalie's chief-of-staff bot on Ryver

1. **Create the bot's own Ryver account** – a Ryver admin invites e.g. `natalie-cos@yourcompany.com`
   (display name "Natalie's Chief of Staff"). Accept the invite, set a strong unique password,
   and add the account only to the teams/forums it should see.
2. **Install**: `python -m venv .venv && . .venv/bin/activate && pip install /path/to/ryver-connector`
3. **Configure**: copy `natalie-cos.env.example` to `~/.config/natalie-cos.env`, `chmod 600`, fill in.
4. **Verify**: `set -a; . ~/.config/natalie-cos.env; set +a; ryver-connector whoami` → shows `natalie-cos`.
5. **Create a Grok Bot webhook routine** (e.g. "When a Ryver event arrives, summarize it for Natalie
   and draft a reply for approval"). Put its URL/key into `RYVER_ALERTS_WEBHOOK_URL/KEY`.
6. **Run the listener**: `ENV_FILE=~/.config/natalie-cos.env scripts/supervise.sh &`
   (or `python examples/listen_to_webhook.py`). Each DM / @mention / watched-room message is
   POSTed as JSON (`kind, source, source_id, sender, sender_username, text, message_id, time, org`).
7. **Reply after approval**: once Natalie approves the draft text, run
   `RYVER_ALLOW_WRITES=1 ryver-connector post dm <user_id> "approved text"` (try `--dry-run` first)
   or `examples/reply_after_approval.py`.
