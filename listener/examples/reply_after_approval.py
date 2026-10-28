"""Post a reply ONLY after a human approved the exact text.

The Grok Bot routine drafts a reply from the webhook event, shows it to the owner,
and once approved runs e.g.:

    RYVER_ALLOW_WRITES=1 python examples/reply_after_approval.py dm 1234 "Thanks, on it."
    RYVER_ALLOW_WRITES=1 python examples/reply_after_approval.py comment 5678 "Done."
Add RYVER_DRY_RUN=1 to preview without sending.
"""
import sys
from ryver_connector import RyverClient, RyverConfig

kind, target, text = sys.argv[1], int(sys.argv[2]), sys.argv[3]
print(f"About to send to {kind} {target}:\n---\n{text}\n---")
if input("Type 'yes' to confirm: ").strip().lower() != "yes":
    sys.exit("aborted")
c = RyverClient(RyverConfig.from_env())
res = c.comment_on_topic(target, text) if kind == "comment" else c.send_message(kind, target, text)
print("sent:", res)
