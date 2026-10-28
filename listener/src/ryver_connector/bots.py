"""Forward events that @mention OTHER bots to each bot's own webhook.

Config file (JSON, chmod 600, holds NO secrets):
  {"quincy": {"webhook_url": "https://...", "webhook_key_env": "RYVER_BOT_QUINCY_WEBHOOK_KEY"}}
The bearer key is read from the named env var at startup. Values are never logged.
Location: $RYVER_BOTS_FILE, else ./bots.json if it exists. Missing file => feature off.
"""
from __future__ import annotations
import json
import logging
import os
import re
import stat
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

log = logging.getLogger("ryver_connector")
HANDLE_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
RESERVED = {"team", "here", "all", "everyone", "channel"}


@dataclass
class BotRoute:
    handle: str
    webhook_url: str = field(repr=False)
    webhook_key: Optional[str] = field(default=None, repr=False)


def mention_regex(handle: str) -> re.Pattern:
    # whole-word @handle; not part of an email (x@handle) and not a prefix (@handlebar / @handle.x)
    return re.compile(r"(?<![\w@.])@" + re.escape(handle) + r"(?![\w\-]|\.\w)", re.I)


def load_bots(path: Optional[str] = None, env=None, exclude: Optional[str] = None) -> List[BotRoute]:
    e = os.environ if env is None else env
    path = path or e.get("RYVER_BOTS_FILE") or ("bots.json" if os.path.exists("bots.json") else None)
    if not path or not os.path.exists(path):
        return []
    try:
        if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            log.warning("bots file %s is group/world accessible; chmod 600 it", path)
    except OSError:
        pass
    with open(path) as f:
        data = json.load(f)
    routes = []
    for handle, spec in (data or {}).items():
        h = str(handle).lstrip("@")
        if h.startswith("_"):
            continue  # comments like "_comment"
        if not HANDLE_RE.match(h) or h.lower() in RESERVED:
            log.warning("bots file: skipping invalid handle %r", h); continue
        if exclude and h.lower() == exclude.lower():
            log.warning("bots file: skipping @%s (that is the listener itself)", h); continue
        url = (spec or {}).get("webhook_url")
        if not url:
            log.warning("bots file: @%s has no webhook_url; skipped", h); continue
        key_env = spec.get("webhook_key_env")
        key = e.get(key_env) if key_env else None
        if key_env and not key:
            log.warning("bots file: env var %s for @%s is not set; skipped", key_env, h); continue
        routes.append(BotRoute(h, url, key))
    log.info("bot mention forwarding enabled for: %s", ", ".join("@" + r.handle for r in routes) or "(none)")
    return routes


class BotRouter:
    def __init__(self, routes: List[BotRoute], sink_factory: Optional[Callable] = None):
        if sink_factory is None:
            from .listener import WebhookSink
            sink_factory = WebhookSink
        self.routes = [(r, mention_regex(r.handle), sink_factory(r.webhook_url, r.webhook_key)) for r in routes]
        self.seen: set = set()

    def __bool__(self) -> bool:
        return bool(self.routes)

    def matches(self, text: str) -> List[str]:
        return [r.handle for r, rx, _ in self.routes if rx.search(text or "")]

    def route(self, ev) -> List[str]:
        sent = []
        for r, rx, sink in self.routes:
            if not rx.search(ev.text or ""):
                continue
            if (ev.sender_username or "").lower() == r.handle.lower():
                continue  # authored by that bot: avoid loops
            k = (r.handle.lower(), ev.message_id)
            if k in self.seen:
                continue
            self.seen.add(k)
            log.info("BOT-ROUTE @%s id=%s", r.handle, ev.message_id)
            try:
                sink(ev)
                sent.append(r.handle)
            except Exception as ex:
                log.warning("bot route @%s error: %s", r.handle, type(ex).__name__)
        if len(self.seen) > 50000:
            self.seen = set(list(self.seen)[-10000:])
        return sent
