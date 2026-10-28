"""Kit: mentions anywhere the bot can see are forwarded with NO watch list; DMs forwarded."""
from ryver_connector import RyverListener, build_mention_regex
from ryver_connector.config import RyverConfig


def mk():
    cfg = RyverConfig(org="jigsawhealth", username="quincy", password="pw")
    assert cfg.watch_rooms == []
    got = []
    L = RyverListener(cfg, [got.append], bot_router=None)
    L.bot_router = None
    L.me = {"id": 7, "username": "quincy", "jid": "q@x"}
    L.ujid = {"q@x": L.me, "c@x": {"id": 8, "username": "carissa", "displayName": "Carissa"}}
    L.rooms = {"cj@x": {"id": 5, "name": "Carissa and Jess", "jid": "cj@x", "_kind": "team"}}
    L.mention_re = build_mention_regex(["quincy"], cfg.group_mentions)
    L.resolve_watched()
    assert L.watched_jids == set()
    return L, got


def chat(to, text, key, frm="c@x"):
    return {"type": "chat", "from": frm, "to": to, "text": text, "key": key}


def test_mention_in_unwatched_room_forwarded():
    L, got = mk()
    ev = L.on_chat(chat("cj@x", "@quincy can you check this?", "m1"))
    assert ev.kind == "mention" and ev.source == "Carissa and Jess"
    assert L.on_chat(chat("cj@x", "@quincyx not you", "m2")) is None
    assert L.on_chat(chat("cj@x", "no mention", "m3")) is None
    assert [e.message_id for e in got] == ["m1"]


def test_dm_forwarded():
    L, got = mk()
    ev = L.on_chat(chat("q@x", "hi Quincy", "d1"))
    assert ev.kind == "dm" and got[0].text == "hi Quincy"


def test_own_messages_skipped():
    L, got = mk()
    assert L.on_chat(chat("cj@x", "@quincy me", "s1", frm="q@x")) is None
    assert L.on_topic_item("cj@x", "topic_reply", "t", 1, L.me, "@quincy", "c-s") is None
    assert got == []


def test_topic_comment_mention_in_unwatched_room_forwarded():
    L, got = mk()
    u = L.ujid["c@x"]
    assert L.on_topic_item("cj@x", "topic_reply", "Carissa and Jess topic: X", 1, u, "ping @Quincy", "comment-1").kind == "mention"
    assert L.on_topic_item("cj@x", "topic", "Carissa and Jess topic: Y", 5, u, "Y\nno mention", "post-2") is None
    assert len(got) == 1


def test_ryver_user_alias():
    c = RyverConfig.from_env({"RYVER_ORG": "jigsawhealth", "RYVER_USER": "quincy", "RYVER_PASSWORD": "x"})
    assert c.username == "quincy" and "x" not in repr(c)
