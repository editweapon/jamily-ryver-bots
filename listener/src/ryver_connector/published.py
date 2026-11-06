"""Published-API listener. Basic auth as a normal member. No websocket, no admin token.

What Ryver publishes (https://api.ryver.com/ryvrest_api_examples.html):
  GET /workrooms and GET /forums
  GET /users
  GET /workrooms(id)/Post.Stream(archived=false) and the same on /forums(id)
  Auth is HTTP Basic with the member's own username and password.

Topic replies, chat history, and DMs have no published read. This module does not
call Chat.History, postComments, userNotifications, or User.Login. See GAPS.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from .bots import BotRouter, load_bots
from .client import RyverAPIError
from .config import RyverConfig
from .listener import Event, WebhookSink, build_mention_regex

log = logging.getLogger("ryver_connector")

# None means the published examples have no read for that source.
COVERAGE = {
    "topic": "GET /workrooms(id)/Post.Stream(archived=false) and GET /forums(id)/Post.Stream(archived=false)",
    "topic_reply": None,
    "chat": None,
    "dm": None,
}

GAPS = (
    "Topic replies have no published read endpoint, so they are not polled.",
    "Chat messages have no published read endpoint (Chat.PostMessage is create-only), so they are not polled.",
    "Direct messages have no published read endpoint, so they are not polled.",
)

STATE_NAME = "published-seen.json"
MAX_SEEN = 5000
MAX_PAGES = 5
LIST_PAGE = 200


def normalize_stamp(value: Optional[str]) -> str:
    """UTC timestamp that sorts as text. Empty stays empty."""
    if not value:
        return ""
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def topic_text(post: Dict[str, Any]) -> str:
    return f"{post.get('subject') or ''}\n{post.get('body') or ''}".strip()


def _create_user(post: Dict[str, Any]) -> Dict[str, Any]:
    cu = post.get("createUser") or {}
    if isinstance(cu, dict):
        return cu
    return {"id": cu}


class SeenState:
    """Ids already handled and a per-room cursor. No secrets."""

    def __init__(self, directory: str):
        self.directory = directory
        self.path = os.path.join(directory, STATE_NAME)
        self.watermarks: Dict[str, str] = {}
        self.seen: List[str] = []
        self.seen_set: set = set()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.warning("published state unreadable (%s); starting a new cursor", type(e).__name__)
            return
        self.watermarks = {str(k): str(v) for k, v in (data.get("watermarks") or {}).items()}
        self.seen = [str(x) for x in (data.get("seen") or [])][-MAX_SEEN:]
        self.seen_set = set(self.seen)

    def mark(self, mid: str) -> None:
        if mid in self.seen_set:
            return
        self.seen.append(mid)
        self.seen_set.add(mid)
        if len(self.seen) > MAX_SEEN:
            drop = self.seen[:-MAX_SEEN]
            self.seen = self.seen[-MAX_SEEN:]
            for old in drop:
                self.seen_set.discard(old)
            self.seen_set.update(self.seen)

    def save(self) -> None:
        os.makedirs(self.directory, exist_ok=True)
        payload = {"version": 1, "watermarks": self.watermarks, "seen": self.seen[-MAX_SEEN:]}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)


class PublishedAPIListener:
    """Poll documented topic streams and forward @mentions. Read-only."""

    def __init__(self, cfg: RyverConfig, callbacks: Optional[List[Callable[[Event], Any]]] = None,
                 jsonl_path: Optional[str] = None, fetcher=None, pause: float = 0.2,
                 bot_router: Optional[BotRouter] = None, max_pages: int = MAX_PAGES):
        if cfg.listener_mode != "rest":
            raise ValueError("PublishedAPIListener requires listener_mode rest")
        if not (cfg.username and cfg.password):
            raise PermissionError(
                "published listener needs RYVER_USER and RYVER_PASSWORD (your own member login, not an admin token)"
            )
        self.cfg = cfg
        self.callbacks = list(callbacks or [])
        if cfg.webhook_url:
            self.callbacks.append(WebhookSink(cfg.webhook_url, cfg.webhook_key))
        self.jsonl_path = jsonl_path
        self.fetcher = fetcher
        self.pause = pause
        self.max_pages = max_pages
        self.http = requests.Session()
        self.timeout = 20
        self.orderby_ok = True
        self.state = SeenState(cfg.state_dir)
        self.state.load()
        self.me: Dict[str, Any] = {}
        self.mention_re = build_mention_regex([cfg.username, *cfg.mention_names], cfg.group_mentions)
        self._logged_start = False
        if bot_router is not None:
            self.bot_router = bot_router
        elif os.environ.get("RYVER_BOTS_FILE"):
            self.bot_router = BotRouter(load_bots(exclude=cfg.username))
        else:
            self.bot_router = BotRouter([])

    def _get(self, path: str, **params) -> Dict[str, Any]:
        if self.fetcher is not None:
            data = self.fetcher(path, params)
            return data if isinstance(data, dict) else {"results": data}
        url = self.cfg.api_url + path
        r = self.http.get(
            url,
            params=params or None,
            auth=(self.cfg.username, self.cfg.password),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        if r.status_code == 400 and params.get("$orderby") and self.orderby_ok:
            self.orderby_ok = False
            log.warning("published topic query $orderby was rejected; continuing with $top and $skip only")
            retried = {k: v for k, v in params.items() if k != "$orderby"}
            return self._get(path, **retried)
        if r.status_code == 401:
            raise PermissionError("login failed: HTTP 401")
        if r.status_code >= 400:
            raise RyverAPIError(r.status_code, path)
        try:
            body = r.json()
        except ValueError:
            raise RyverAPIError(r.status_code, path)
        d = body.get("d", body) if isinstance(body, dict) else body
        return d if isinstance(d, dict) else {"results": d}

    def _list(self, path: str, select: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        skip = 0
        while True:
            batch = self._get(path, **{"$select": select, "$top": LIST_PAGE, "$skip": skip}).get("results") or []
            out.extend(batch)
            if len(batch) < LIST_PAGE:
                return out
            skip += len(batch)

    def _load_directory(self) -> List[Dict[str, Any]]:
        users = self._list("/users", "id,username,displayName")
        uname = (self.cfg.username or "").lower()
        me = next((u for u in users if (u.get("username") or "").lower() == uname), None)
        if not me:
            raise PermissionError("RYVER_USER was not found in GET /users. Check the username. No admin account is required.")
        self.me = me
        self.mention_re = build_mention_regex(
            [me.get("username") or self.cfg.username, *self.cfg.mention_names], self.cfg.group_mentions)
        rooms = []
        for team in self._list("/workrooms", "id,name"):
            rooms.append({"kind": "team", "id": team["id"], "name": team.get("name") or str(team["id"])})
        for forum in self._list("/forums", "id,name"):
            rooms.append({"kind": "forum", "id": forum["id"], "name": forum.get("name") or str(forum["id"])})
        if not self._logged_start:
            log.info("published listener as @%s, %d teams, %d forums, poll %ds",
                     me.get("username"), sum(r["kind"] == "team" for r in rooms),
                     sum(r["kind"] == "forum" for r in rooms), self.cfg.poll_interval)
            for line in GAPS:
                log.info("published listener gap: %s", line)
            self._logged_start = True
        return rooms

    def _stream_path(self, kind: str, room_id: Any) -> str:
        coll = "workrooms" if kind == "team" else "forums"
        return f"/{coll}({int(room_id)})/Post.Stream(archived=false)"

    def _fetch_posts(self, room: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
        primed = key in self.state.watermarks
        posts: List[Dict[str, Any]] = []
        skip = 0
        for _ in range(self.max_pages):
            params: Dict[str, Any] = {"$format": "json", "$top": self.cfg.poll_top, "$skip": skip}
            if self.orderby_ok:
                params["$orderby"] = "createDate desc"
            batch = self._get(self._stream_path(room["kind"], room["id"]), **params).get("results") or []
            posts.extend(batch)
            if not primed or len(batch) < self.cfg.poll_top:
                break
            stamps = [normalize_stamp(p.get("createDate")) for p in batch]
            oldest = min(stamps) if stamps else ""
            wm = self.state.watermarks.get(key) or ""
            if not oldest or (wm and oldest <= wm):
                break
            skip += len(batch)
            if self.pause:
                time.sleep(self.pause)
        return posts

    def _sender_name(self, user: Dict[str, Any]) -> str:
        return user.get("displayName") or user.get("username") or user.get("__descriptor") or "unknown"

    def _forward(self, room: Dict[str, Any], post: Dict[str, Any], mid: str) -> Optional[Event]:
        user = _create_user(post)
        if user.get("id") == self.me.get("id"):
            return None
        text = topic_text(post)
        if not self.mention_re.search(text):
            return None
        ev = Event(
            kind="mention",
            source=f"{room['name']} topic: {post.get('subject') or ''}".strip(),
            source_id=room["id"],
            sender=self._sender_name(user),
            sender_username=user.get("username"),
            text=text,
            message_id=mid,
            time=datetime.now(timezone.utc).isoformat(),
            org=self.cfg.org,
        )
        return ev

    def _deliver(self, ev: Event) -> bool:
        if self.bot_router:
            try:
                self.bot_router.route(ev)
            except Exception:
                log.warning("bot routing error")
        ok = True
        for cb in self.callbacks:
            try:
                if isinstance(cb, WebhookSink):
                    if not cb.send_sync(ev):
                        ok = False
                elif cb(ev) is False:
                    ok = False
            except Exception as e:
                log.warning("callback error: %s", type(e).__name__)
                ok = False
        if ok and self.jsonl_path:
            try:
                with open(self.jsonl_path, "a") as f:
                    f.write(json.dumps(ev.to_dict()) + "\n")
            except OSError as e:
                log.warning("jsonl write failed: %s", type(e).__name__)
                ok = False
        if ok:
            log.info("EVENT %s in %s from %s id=%s", ev.kind, ev.source, ev.sender, ev.message_id)
        return ok

    def _baseline(self, key: str, posts: List[Dict[str, Any]]) -> None:
        stamps = []
        for post in posts:
            if post.get("id") is None:
                continue
            self.state.mark(f"post-{post['id']}")
            stamp = normalize_stamp(post.get("createDate"))
            if stamp:
                stamps.append(stamp)
        self.state.watermarks[key] = max(stamps) if stamps else ""
        self.state.save()

    def _consume_room(self, room: Dict[str, Any]) -> List[Event]:
        key = f"{room['kind']}:{room['id']}"
        try:
            posts = self._fetch_posts(room, key)
        except PermissionError:
            raise
        except Exception as e:
            log.warning("published poll error in %s: %s", room.get("name"), type(e).__name__)
            return []
        if key not in self.state.watermarks:
            self._baseline(key, posts)
            if self.pause:
                time.sleep(self.pause)
            return []
        emitted: List[Event] = []
        wm = self.state.watermarks.get(key) or ""
        ordered = sorted(posts, key=lambda p: normalize_stamp(p.get("createDate")))
        for post in ordered:
            if post.get("id") is None:
                continue
            mid = f"post-{post['id']}"
            stamp = normalize_stamp(post.get("createDate"))
            if mid in self.state.seen_set:
                if stamp and stamp > wm:
                    wm = stamp
                continue
            if wm and stamp and stamp < wm:
                self.state.mark(mid)
                continue
            ev = self._forward(room, post, mid)
            if ev is not None and not self._deliver(ev):
                self.state.watermarks[key] = wm
                self.state.save()
                return emitted
            if ev is not None:
                emitted.append(ev)
            self.state.mark(mid)
            if stamp and stamp > wm:
                wm = stamp
        self.state.watermarks[key] = wm
        self.state.save()
        if self.pause:
            time.sleep(self.pause)
        return emitted

    def _safe(self, exc: BaseException) -> str:
        text = f"{type(exc).__name__}: {exc}"
        secret = self.cfg.password or ""
        if secret and secret in text:
            text = text.replace(secret, "***")
        return text

    def poll_once(self) -> List[Event]:
        rooms = self._load_directory()
        emitted: List[Event] = []
        for room in rooms:
            emitted.extend(self._consume_room(room))
        return emitted

    async def run(self, max_backoff: int = 300) -> None:
        back = 2
        while True:
            try:
                await asyncio.to_thread(self.poll_once)
                back = 2
                while True:
                    await asyncio.sleep(self.cfg.poll_interval)
                    await asyncio.to_thread(self.poll_once)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("published listener error: %s; retry in %ss", self._safe(e), back)
            await asyncio.sleep(back + random.random())
            back = min(back * 2, max_backoff)
