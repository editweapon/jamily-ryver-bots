"""Live listener over Ryver's (undocumented) chat websocket + topic polling fallback.

Emits Event objects for: DMs to the bot, @mentions of the bot (and @team/@here/@all),
and any message in watched rooms. Events go to a callback and/or a JSON webhook (Bearer auth).
Read-only: never posts, never marks anything read.
"""
from __future__ import annotations
import asyncio
import json
import os
import logging
import random
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import aiohttp

from .config import RyverConfig
from .bots import BotRouter, load_bots

log = logging.getLogger("ryver_connector")
QUIET = {"ack", "presence_changed", "presence_change", "user_typing", "pong", "event"}


@dataclass
class Event:
    kind: str            # dm | mention | watched_chat | topic | topic_reply
    source: str          # human readable room name / "DM"
    source_id: Any
    sender: str
    sender_username: Optional[str]
    text: str
    message_id: str
    time: str
    org: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_mention_regex(names: Iterable[str], groups: Iterable[str]) -> re.Pattern:
    alts = [re.escape(n.lstrip("@")) for n in list(names) + list(groups) if n]
    return re.compile(r"(?<![\w@])@(" + "|".join(alts) + r")\b", re.I) if alts else re.compile(r"(?!x)x")


class WebhookSink:
    """POST events as JSON with 'Authorization: Bearer <key>'; retries w/ backoff in a thread."""

    def __init__(self, url: str, key: Optional[str], retries: int = 3, timeout: float = 5):
        self.url, self._key, self.retries, self.timeout = url, key, retries, timeout

    def send_sync(self, ev: Event) -> bool:
        data = json.dumps(ev.to_dict()).encode()
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = "Bearer " + self._key
        for i in range(self.retries):
            try:
                req = urllib.request.Request(self.url, data=data, method="POST", headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    st = r.status
            except urllib.error.HTTPError as e:
                st = e.code
            except Exception as e:  # network error
                st = type(e).__name__
            if isinstance(st, int) and 200 <= st < 300:
                log.info("webhook ok id=%s status=%s", ev.message_id, st)
                return True
            log.warning("webhook fail id=%s status=%s attempt=%d", ev.message_id, st, i + 1)
            if i < self.retries - 1:
                time.sleep(2 ** i)
        return False

    def __call__(self, ev: Event) -> None:
        threading.Thread(target=self.send_sync, args=(ev,), daemon=True).start()


class RyverListener:
    def __init__(self, cfg: RyverConfig, callbacks: Optional[List[Callable[[Event], Any]]] = None,
                 jsonl_path: Optional[str] = None, poll_topics: bool = True,
                 bot_router: Optional[BotRouter] = None):
        self.cfg = cfg
        self.bot_router = bot_router if bot_router is not None else BotRouter(load_bots(exclude=cfg.username) if os.environ.get("RYVER_BOTS_FILE") else [])
        self.callbacks = list(callbacks or [])
        if cfg.webhook_url:
            self.callbacks.append(WebhookSink(cfg.webhook_url, cfg.webhook_key))
        self.jsonl_path = jsonl_path
        self.poll_topics = poll_topics
        self.seen: set = set()
        self.users: Dict[int, Dict] = {}
        self.ujid: Dict[str, Dict] = {}
        self.rooms: Dict[str, Dict] = {}   # jid -> {id,name,jid,_kind}
        self.watched_jids: set = set()
        self.me: Dict[str, Any] = {}
        self.mention_re = build_mention_regex([], cfg.group_mentions)

    # ---------- REST (async) ----------
    async def login(self, http: aiohttp.ClientSession) -> None:
        c = self.cfg
        if c.username and c.password:
            r = await http.post(f"{c.api_url}/User.Login(client='pyryver')",
                                auth=aiohttp.BasicAuth(c.username, c.password), headers={"Accept": "application/json"})
            if r.status != 200:
                raise PermissionError(f"login failed: HTTP {r.status}")
            d = (await r.json())["d"]
            sid, me_id, self.ws_url = d["sessionId"], d["id"], d["services"]["chat"]
        else:
            sid = c.token
            self.h = {"Authorization": "Session " + sid, "Accept": "application/json"}
            d = await self.get(http, "/Ryver.Info()")
            me_id, self.ws_url = d["me"]["id"], d["services"]["chat"]
        self.h = {"Authorization": "Session " + sid, "Accept": "application/json"}
        self.me_id = me_id
        await self.load(http)

    async def get(self, http, path: str) -> Any:
        r = await http.get(self.cfg.api_url + path, headers=self.h)
        if r.status == 401:
            raise PermissionError("session expired")
        r.raise_for_status()
        return (await r.json())["d"]

    async def load(self, http) -> None:
        skip = 0
        while True:
            res = (await self.get(http, f"/users?$select=id,username,displayName,jid&$top=500&$skip={skip}"))["results"]
            if not res:
                break
            for u in res:
                self.users[u["id"]] = u
                self.ujid[u.get("jid")] = u
            skip += len(res)
        for coll, kind in (("workrooms", "team"), ("forums", "forum")):
            for w in (await self.get(http, f"/{coll}?$select=id,name,jid&$top=500"))["results"]:
                self.rooms[w["jid"]] = {**w, "_kind": kind}
        me = (await self.get(http, f"/users?$filter=id eq {self.me_id}&$select=id,username,displayName,jid"))["results"][0]
        self.me = me
        self.users[me["id"]] = me
        self.ujid[me["jid"]] = me
        self.mention_re = build_mention_regex([me["username"], *self.cfg.mention_names], self.cfg.group_mentions)
        self.resolve_watched()
        log.info("loaded %d users, %d rooms, watching %d rooms as @%s",
                 len(self.users), len(self.rooms), len(self.watched_jids), me["username"])

    def resolve_watched(self) -> None:
        want = {w.lower() for w in self.cfg.watch_rooms}
        self.watched_jids = {j for j, r in self.rooms.items()
                             if str(r["id"]) in want or (r.get("name") or "").lower() in want}

    # ---------- classification ----------
    def _name(self, u: Optional[Dict]) -> Optional[str]:
        return u and (u.get("displayName") or u.get("username"))

    def _event(self, kind, source, source_id, sender_u, text, mid) -> Event:
        return Event(kind=kind, source=source, source_id=source_id,
                     sender=self._name(sender_u) or "unknown",
                     sender_username=(sender_u or {}).get("username"), text=text or "",
                     message_id=str(mid), time=datetime.now(timezone.utc).isoformat(), org=self.cfg.org)

    def route_bots(self, ev: Event) -> None:
        if self.bot_router:
            try:
                self.bot_router.route(ev)
            except Exception as e:
                log.warning("bot routing error: %s", type(e).__name__)

    def emit(self, kind, source, source_id, sender_u, text, mid) -> Optional[Event]:
        if not mid or mid in self.seen:
            return None
        self.seen.add(mid)
        if len(self.seen) > 50000:
            self.seen = set(list(self.seen)[-10000:])
        ev = self._event(kind, source, source_id, sender_u, text, mid)
        self.route_bots(ev)
        log.info("EVENT %s in %s from %s id=%s", kind, source, ev.sender, mid)
        if self.jsonl_path:
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(ev.to_dict()) + "\n")
        for cb in self.callbacks:
            try:
                cb(ev)
            except Exception as e:
                log.warning("callback error: %s", e)
        return ev

    def on_chat(self, m: Dict[str, Any]) -> Optional[Event]:
        frm, to = m.get("from", ""), m.get("to", "")
        text, mid = m.get("text") or "", m.get("key") or m.get("id")
        su = self.ujid.get(frm)
        if su and su.get("id") == self.me.get("id"):
            return None
        room = self.rooms.get(to)
        if to == self.me.get("jid"):
            return self.emit("dm", "DM", su and su["id"], su, text, mid)
        if self.mention_re.search(text):
            return self.emit("mention", (room or {}).get("name", to), room and room["id"], su, text, mid)
        if to in self.watched_jids:
            return self.emit("watched_chat", room["name"], room["id"], su, text, mid)
        # Not a @peter event: still forward to other bots it mentions (peter's sinks untouched).
        if mid and self.bot_router and self.bot_router.matches(text):
            self.route_bots(self._event("bot_mention", (room or {}).get("name", to), room and room["id"], su, text, mid))
        return None

    # ---------- websocket ----------
    async def wsloop(self, http) -> None:
        async with http.ws_connect(self.ws_url, heartbeat=None) as ws:
            await ws.send_json({"type": "auth", "authorization": self.h["Authorization"],
                                "agent": "Ryver", "resource": f"Contatta-{int(time.time() * 1000)}"})

            async def pinger():
                while True:
                    await asyncio.sleep(10)
                    await ws.send_json({"type": "ping", "id": str(int(time.time() * 1000))})

            pt = asyncio.create_task(pinger())
            try:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    m = json.loads(msg.data)
                    t = m.get("type")
                    if t == "chat":
                        self.on_chat(m)
                    elif t not in QUIET:
                        log.debug("ws event type=%s", t)
            finally:
                pt.cancel()
        raise ConnectionError("websocket closed")

    # ---------- topic polling: ALL rooms the bot can see ----------
    def _topic_wanted(self, jid: str, text: Optional[str]) -> bool:
        """Watched rooms: every topic/comment. Other rooms: only ones that @mention the bot."""
        return jid in self.watched_jids or bool(self.mention_re.search(text or ""))

    def on_topic_item(self, jid: str, kind: str, source: str, source_id, user, text, mid) -> Optional[Event]:
        if (user or {}).get("id") == self.me.get("id") or not self._topic_wanted(jid, text):
            return None
        if jid not in self.watched_jids:
            kind = "mention"
        return self.emit(kind, source, source_id, user, text, mid)

    async def poll(self, http) -> None:
        last: Dict[str, str] = {}
        while True:
            for jid in list(self.rooms):
                r = self.rooms[jid]
                coll = "workrooms" if r["_kind"] == "team" else "forums"
                try:
                    ps = (await self.get(http, f"/{coll}({r['id']})/Post.Stream()?$top=20&$orderby=modifyDate desc"
                                               "&$select=id,subject,body,createDate,lastReplyDate,createUser&$expand=createUser"))["results"]
                    base = last.get(jid)
                    for p in ps:
                        stamp = max(p.get("createDate") or "", p.get("lastReplyDate") or "")
                        if base and stamp > base:
                            cu = self.users.get(p["createUser"]["id"], p["createUser"])
                            if p["createDate"] > base:
                                self.on_topic_item(jid, "topic", f"{r['name']} topic: {p['subject']}", r["id"], cu,
                                                   f"{p.get('subject') or ''}\n{p.get('body') or ''}", f"post-{p['id']}")
                            cs = (await self.get(http, f"/postComments?$filter=post/id eq {p['id']}&$orderby=createDate desc"
                                                       "&$top=20&$select=id,comment,createDate,createUser&$expand=createUser"))["results"]
                            for c in cs:
                                cu2 = self.users.get(c["createUser"]["id"], c["createUser"])
                                if c["createDate"] > base:
                                    self.on_topic_item(jid, "topic_reply", f"{r['name']} topic: {p['subject']}", p["id"], cu2,
                                                       c.get("comment"), f"comment-{c['id']}")
                    if ps:
                        last[jid] = max([base or ""] + [max(p.get("createDate") or "", p.get("lastReplyDate") or "") for p in ps])
                except PermissionError:
                    raise
                except Exception as e:
                    log.warning("poll error in %s: %s", r.get("name"), e)
                await asyncio.sleep(0.2)  # be gentle when a bot is in many rooms
            await asyncio.sleep(self.cfg.poll_interval)

    # ---------- main loop with reconnect/backoff ----------
    async def run(self, max_backoff: int = 300) -> None:
        back = 2
        while True:
            try:
                async with aiohttp.ClientSession() as http:
                    await self.login(http)
                    back = 2
                    tasks = [asyncio.create_task(self.poll(http))] if self.poll_topics else []
                    try:
                        await self.wsloop(http)
                    finally:
                        for t in tasks:
                            t.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("loop error: %s: %s; reconnect in %ss", type(e).__name__, e, back)
            await asyncio.sleep(back + random.random())
            back = min(back * 2, max_backoff)
