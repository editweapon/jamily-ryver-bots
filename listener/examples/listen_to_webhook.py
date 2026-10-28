"""Run the listener for a chief-of-staff bot and forward events to a Grok Bot webhook routine.

    set -a; . ~/.config/natalie-cos.env; set +a
    python examples/listen_to_webhook.py
"""
import asyncio, logging
from ryver_connector import RyverConfig, RyverListener

logging.basicConfig(level=logging.INFO)
cfg = RyverConfig.from_env()           # RYVER_ALERTS_WEBHOOK_URL/KEY -> WebhookSink is added automatically


def local_note(ev):                    # optional extra in-process callback
    print(f"[{ev.kind}] {ev.source} / {ev.sender}: {ev.text[:120]}")


asyncio.run(RyverListener(cfg, callbacks=[local_note], jsonl_path=f"{cfg.state_dir}/events.jsonl").run())
