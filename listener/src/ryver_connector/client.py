"""Synchronous Ryver REST (OData) client.

Reads are always allowed. Writes require cfg.allow_writes (RYVER_ALLOW_WRITES=1);
with cfg.dry_run (RYVER_DRY_RUN=1) writes are logged/returned but never sent.
Nothing in this client marks messages as read.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Iterator, List, Optional

import requests

from .config import RyverConfig

log = logging.getLogger("ryver_connector")

# chat-capable entity kinds -> OData collection
KINDS = {"forum": "forums", "team": "workrooms", "workroom": "workrooms", "user": "users", "dm": "users"}


class RyverAPIError(RuntimeError):
    def __init__(self, status: int, msg: str):
        super().__init__(f"HTTP {status}: {msg}")
        self.status = status


class WritesDisabledError(PermissionError):
    pass


def _collection(kind: str) -> str:
    try:
        return KINDS[kind.lower()]
    except KeyError:
        raise ValueError(f"unknown chat kind {kind!r}; use forum, team or dm")


class RyverClient:
    def __init__(self, cfg: RyverConfig, session: Optional[requests.Session] = None, timeout: float = 20):
        self.cfg = cfg
        self.http = session or requests.Session()
        self.timeout = timeout
        self.session_id: Optional[str] = cfg.token
        self.me: Optional[Dict[str, Any]] = None
        self.chat_ws_url: Optional[str] = None

    # ---------- auth ----------
    def login(self) -> Dict[str, Any]:
        """pyryver-style login: returns session id and websocket URL."""
        if self.cfg.username and self.cfg.password:
            r = self.http.post(f"{self.cfg.api_url}/User.Login(client='pyryver')",
                               auth=(self.cfg.username, self.cfg.password),
                               headers={"Accept": "application/json"}, timeout=self.timeout)
            if r.status_code != 200:
                raise RyverAPIError(r.status_code, "login failed (check RYVER_USERNAME / RYVER_PASSWORD)")
            d = r.json()["d"]
            self.session_id = d["sessionId"]
            self.chat_ws_url = (d.get("services") or {}).get("chat")
            self._me_id = d.get("id")
            return d
        if not self.session_id:
            raise RyverAPIError(401, "no credentials")
        d = self._get("/Ryver.Info()")
        self.chat_ws_url = (d.get("services") or {}).get("chat")
        self._me_id = (d.get("me") or {}).get("id")
        return d

    @property
    def headers(self) -> Dict[str, str]:
        if not self.session_id:
            self.login()
        return {"Authorization": "Session " + self.session_id, "Accept": "application/json"}

    # ---------- low level ----------
    def _req(self, method: str, path: str, **kw) -> Any:
        r = self.http.request(method, self.cfg.api_url + path, headers=self.headers, timeout=self.timeout, **kw)
        if r.status_code == 401 and self.cfg.username and self.cfg.password:
            self.login()
            r = self.http.request(method, self.cfg.api_url + path, headers=self.headers, timeout=self.timeout, **kw)
        if r.status_code >= 400:
            raise RyverAPIError(r.status_code, r.text[:300])
        if not r.content:
            return None
        body = r.json()
        return body.get("d", body) if isinstance(body, dict) else body

    def _get(self, path: str, **params) -> Any:
        return self._req("GET", path, params=params or None)

    def _paged(self, path: str, page: int = 500, **params) -> Iterator[Dict[str, Any]]:
        skip = 0
        while True:
            res = self._get(path, **{"$top": page, "$skip": skip, **params})["results"]
            if not res:
                return
            yield from res
            skip += len(res)
            if len(res) < page:
                return

    def _write(self, method: str, path: str, payload: Dict[str, Any]) -> Any:
        if not self.cfg.allow_writes:
            raise WritesDisabledError("writes are disabled; set RYVER_ALLOW_WRITES=1 to enable")
        if self.cfg.dry_run:
            log.info("DRY RUN %s %s %s", method, path, payload)
            return {"dry_run": True, "method": method, "path": path, "payload": payload}
        return self._req(method, path, json=payload)

    # ---------- reads ----------
    def whoami(self) -> Dict[str, Any]:
        if not self.session_id or not getattr(self, "_me_id", None):
            self.login()
        res = self._get("/users", **{"$filter": f"id eq {self._me_id}",
                                      "$select": "id,username,displayName,emailAddress,jid"})["results"]
        self.me = res[0] if res else {"id": self._me_id}
        return self.me

    def list_users(self) -> List[Dict[str, Any]]:
        return list(self._paged("/users", **{"$select": "id,username,displayName,jid,active"}))

    def list_teams(self) -> List[Dict[str, Any]]:
        return list(self._paged("/workrooms", **{"$select": "id,name,jid"}))

    def list_forums(self) -> List[Dict[str, Any]]:
        return list(self._paged("/forums", **{"$select": "id,name,jid"}))

    def list_topics(self, kind: str, chat_id: int, top: int = 20) -> List[Dict[str, Any]]:
        return self._get(f"/{_collection(kind)}({chat_id})/Post.Stream()", **{
            "$top": top, "$orderby": "modifyDate desc",
            "$select": "id,subject,body,createDate,lastReplyDate,createUser", "$expand": "createUser"})["results"]

    def topic_comments(self, post_id: int, top: int = 50) -> List[Dict[str, Any]]:
        return self._get("/postComments", **{
            "$filter": f"post/id eq {post_id}", "$orderby": "createDate desc", "$top": top,
            "$select": "id,comment,createDate,createUser", "$expand": "createUser"})["results"]

    def chat_history(self, kind: str, chat_id: int, top: int = 50) -> List[Dict[str, Any]]:
        """Recent chat messages for a forum, team, or DM (kind='dm', chat_id=user id). Does not mark read."""
        d = self._get(f"/{_collection(kind)}({chat_id})/Chat.History()", **{"$format": "json", "$top": top})
        return d.get("results", d) if isinstance(d, dict) else d

    def dm_history(self, user_id: int, top: int = 50) -> List[Dict[str, Any]]:
        return self.chat_history("dm", user_id, top)

    def find_user(self, username: str) -> Optional[Dict[str, Any]]:
        u = username.lstrip("@").lower()
        res = self._get("/users", **{"$filter": f"username eq '{u}'", "$select": "id,username,displayName,jid"})["results"]
        return res[0] if res else None

    # ---------- writes (gated) ----------
    def send_message(self, kind: str, chat_id: int, text: str) -> Any:
        return self._write("POST", f"/{_collection(kind)}({chat_id})/Chat.PostMessage()", {"body": text})

    def post_topic(self, kind: str, chat_id: int, subject: str, body: str) -> Any:
        etype = {"forums": "Entity.Forum", "workrooms": "Entity.Workroom", "users": "Entity.User"}[_collection(kind)]
        return self._write("POST", "/posts", {
            "subject": subject, "body": body, "recordType": "note",
            "outAssociations": {"results": [{"inSecured": True, "inType": etype, "inId": chat_id}]}})

    def comment_on_topic(self, post_id: int, text: str) -> Any:
        return self._write("POST", "/postComments", {"post": {"id": post_id}, "comment": text})

    def react(self, kind: str, chat_id: int, message_id: str, emoji: str) -> Any:
        return self._write("POST", f"/{_collection(kind)}({chat_id})/Chat.React()",
                           {"id": message_id, "reaction": emoji.strip(":")})
