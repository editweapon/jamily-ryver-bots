import json, os
from ryver_connector import RyverListener, BotRoute, BotRouter, load_bots, build_mention_regex, Event
from ryver_connector.bots import mention_regex

class Rec:
    calls = []
    def __init__(self, url, key): self.url, self.key = url, key
    def __call__(self, ev): Rec.calls.append((self.url, self.key, ev))

def router(*handles):
    Rec.calls = []
    return BotRouter([BotRoute(h, f"https://hook/{h}", f"K-{h}") for h in handles], sink_factory=Rec)

def mk(cfg, r):
    got = []
    cfg.watch_rooms = ["Ops"]
    L = RyverListener(cfg, [got.append], bot_router=r)
    L.me = {"id": 7, "username": "bot", "jid": "bot@x"}
    L.ujid = {"bot@x": L.me, "al@x": {"id": 8, "username": "al", "displayName": "Al"},
              "q@x": {"id": 9, "username": "quincy", "displayName": "Quincy"}}
    L.rooms = {"ops@x": {"id": 1, "name": "Ops", "jid": "ops@x", "_kind": "team"},
               "gen@x": {"id": 2, "name": "General", "jid": "gen@x", "_kind": "forum"}}
    L.mention_re = build_mention_regex(["bot"], cfg.group_mentions)
    L.resolve_watched()
    return L, got

def chat(to, text, key, frm="al@x"):
    return {"type": "chat", "from": frm, "to": to, "text": text, "key": key}

def test_regex():
    rx = mention_regex("quincy")
    for t in ["@quincy hi", "hey @Quincy.", "(@quincy)", "@quincy, ok", "x\n@quincy"]:
        assert rx.search(t), t
    for t in ["quincy", "a@quincy.com", "@quincyx", "@quincy_bot", "@@quincy", "@quincy-2", "@team", "@here"]:
        assert not rx.search(t), t

def test_routes_unwatched_room_without_affecting_peter(cfg):
    L, got = mk(cfg, router("quincy"))
    assert L.on_chat(chat("gen@x", "@quincy deploy?", "1")) is None
    assert got == []
    assert len(Rec.calls) == 1
    url, key, ev = Rec.calls[0]
    assert (url, key, ev.kind, ev.message_id, ev.source) == ("https://hook/quincy", "K-quincy", "bot_mention", "1", "General")

def test_routes_alongside_peter_events(cfg):
    L, got = mk(cfg, router("quincy", "zed"))
    assert L.on_chat(chat("ops@x", "@quincy and @bot", "2")).kind == "mention"
    assert L.on_chat(chat("ops@x", "fyi @zed", "3")).kind == "watched_chat"
    assert [e.kind for e in got] == ["mention", "watched_chat"]
    assert [(c[0], c[2].kind) for c in Rec.calls] == [("https://hook/quincy", "mention"), ("https://hook/zed", "watched_chat")]

def test_skip_self_group_and_dupes(cfg):
    L, got = mk(cfg, router("quincy"))
    L.on_chat(chat("gen@x", "@quincy I said", "4", frm="q@x"))
    L.on_chat(chat("gen@x", "@here @team all", "5"))
    L.on_chat(chat("gen@x", "@quincy once", "6"))
    L.on_chat(chat("gen@x", "@quincy once", "6"))
    assert [c[2].message_id for c in Rec.calls] == ["6"]

def test_topic_emit_routes(cfg):
    L, got = mk(cfg, router("quincy"))
    L.emit("topic_reply", "Ops topic: x", 5, {"id": 8, "username": "al"}, "ping @quincy", "comment-9")
    assert got[0].kind == "topic_reply" and Rec.calls[0][2].message_id == "comment-9"

def test_no_bots_noop(cfg):
    L, got = mk(cfg, router())
    assert L.on_chat(chat("gen@x", "@quincy", "7")) is None and Rec.calls == []

def test_load_bots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_bots(env={}) == []
    p = tmp_path / "bots.json"
    p.write_text(json.dumps({"_comment": "x", "@quincy": {"webhook_url": "https://q", "webhook_key_env": "QK"},
                             "nokey": {"webhook_url": "https://n", "webhook_key_env": "MISSING"},
                             "here": {"webhook_url": "https://h"}, "bot": {"webhook_url": "https://b"},
                             "nourl": {}}))
    os.chmod(p, 0o600)
    rs = load_bots(env={"QK": "secret"}, exclude="bot")
    assert [(r.handle, r.webhook_url, r.webhook_key) for r in rs] == [("quincy", "https://q", "secret")]
    assert "secret" not in repr(rs) and "https://q" not in repr(rs)
    assert [r.handle for r in load_bots(env={"RYVER_BOTS_FILE": str(p), "QK": "s"})] == ["quincy", "bot"]

def test_real_sink_bearer(monkeypatch):
    seen = {}
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake(req, timeout):
        seen["auth"] = req.get_header("Authorization"); seen["url"] = req.full_url
        seen["body"] = json.loads(req.data); return Resp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    from ryver_connector import WebhookSink
    r = BotRouter([BotRoute("quincy", "https://q/hook", "QKEY")],
                  sink_factory=lambda u, k: WebhookSink(u, k).send_sync)
    r.route(Event("mention", "Ops", 1, "Al", "al", "@quincy hi", "m1", "t", "acme"))
    assert seen == {"auth": "Bearer QKEY", "url": "https://q/hook", "body": seen["body"]}
    assert seen["body"]["text"] == "@quincy hi"
