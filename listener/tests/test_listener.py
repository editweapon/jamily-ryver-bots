import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from ryver_connector import RyverListener, WebhookSink, Event, build_mention_regex

def mk(cfg, **kw):
    got = []
    cfg.watch_rooms = ["Ops"]
    L = RyverListener(cfg, [got.append], **kw)
    L.me = {"id": 7, "username": "bot", "jid": "bot@x"}
    L.ujid = {"bot@x": L.me, "al@x": {"id": 8, "username": "al", "displayName": "Al"}}
    L.rooms = {"ops@x": {"id": 1, "name": "Ops", "jid": "ops@x", "_kind": "team"},
               "gen@x": {"id": 2, "name": "General", "jid": "gen@x", "_kind": "forum"}}
    L.mention_re = build_mention_regex(["bot"], cfg.group_mentions)
    L.resolve_watched()
    return L, got

def chat(to, text, key, frm="al@x"):
    return {"type": "chat", "from": frm, "to": to, "text": text, "key": key}

def test_filters(cfg):
    L, got = mk(cfg)
    assert L.on_chat(chat("bot@x", "hi", "1")).kind == "dm"
    assert L.on_chat(chat("gen@x", "hey @bot", "2")).kind == "mention"
    assert L.on_chat(chat("gen@x", "@here lunch", "3")).kind == "mention"
    assert L.on_chat(chat("ops@x", "fyi", "4")).kind == "watched_chat"
    assert L.on_chat(chat("gen@x", "nothing", "5")) is None
    assert L.on_chat(chat("gen@x", "email bot@botany.com", "6")) is None
    assert L.on_chat(chat("bot@x", "self", "7", frm="bot@x")) is None
    assert L.on_chat(chat("bot@x", "dup", "1")) is None
    assert [e.kind for e in got] == ["dm", "mention", "mention", "watched_chat"]
    assert got[0].sender == "Al" and got[0].org == "acme"

def test_group_mentions_off(cfg):
    cfg.group_mentions = []
    L, got = mk(cfg)
    assert L.on_chat(chat("gen@x", "@all hi", "a")) is None

def test_jsonl(cfg, tmp_path):
    p = tmp_path / "e.jsonl"
    L, _ = mk(cfg, jsonl_path=str(p))
    L.on_chat(chat("bot@x", "hi", "z"))
    assert json.loads(p.read_text())["message_id"] == "z"

def test_webhook_bearer():
    seen = {}
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers["Authorization"]
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    ev = Event("dm", "DM", 8, "Al", "al", "hi", "m1", "t", "acme")
    assert WebhookSink(f"http://127.0.0.1:{srv.server_port}/", "KEY").send_sync(ev)
    assert seen["auth"] == "Bearer KEY" and seen["body"]["text"] == "hi"
    srv.server_close()

def test_webhook_failure_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    ev = Event("dm", "DM", 8, "Al", "al", "hi", "m1", "t", "acme")
    assert WebhookSink("http://127.0.0.1:1/", "K", retries=2, timeout=0.5).send_sync(ev) is False
