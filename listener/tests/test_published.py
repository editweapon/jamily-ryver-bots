"""Published REST listener: topic mentions, dedupe, restart, and the documented gaps."""
import base64
import json
import re
from pathlib import Path

import pytest
import responses

from ryver_connector import Event, PublishedAPIListener, RyverConfig, RyverListener
from ryver_connector.cli import build_listener
from ryver_connector.published import COVERAGE, GAPS, normalize_stamp

API = "https://jigsawhealth.ryver.com/api/1/odata.svc"


def post(pid, when, subject, body, user=8, username="carissa"):
    return {
        "id": pid,
        "subject": subject,
        "body": body,
        "createDate": when,
        "createUser": {"id": user, "username": username, "displayName": "Carissa"},
    }


class FakeRyver:
    def __init__(self):
        self.calls = []
        self.team_posts = []
        self.forum_posts = []

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "/users":
            return {"results": [{"id": 7, "username": "clara", "displayName": "Clara"}]}
        if path == "/workrooms":
            return {"results": [{"id": 1, "name": "Ops"}]}
        if path == "/forums":
            return {"results": [{"id": 2, "name": "General"}]}
        if path.startswith("/workrooms("):
            return {"results": self._page(self.team_posts, params)}
        if path.startswith("/forums("):
            return {"results": self._page(self.forum_posts, params)}
        raise AssertionError(path)

    @staticmethod
    def _page(posts, params):
        ordered = sorted(posts, key=lambda p: p.get("createDate") or "", reverse=True)
        skip = int(params.get("$skip") or 0)
        top = int(params.get("$top") or 50)
        return list(ordered[skip:skip + top])


def make(tmp_path, fake, **kw):
    cfg = RyverConfig(
        org="jigsawhealth", username="clara", password="s3cret-value",
        state_dir=str(tmp_path), listener_mode="rest", poll_interval=60, poll_top=kw.pop("poll_top", 50),
    )
    got = []
    listener = PublishedAPIListener(cfg, [got.append], fetcher=fake, pause=0, bot_router=None, **kw)
    return listener, got


def test_coverage_names_all_three_sources_and_dms():
    assert COVERAGE["topic"].startswith("GET")
    assert COVERAGE["topic_reply"] is None
    assert COVERAGE["chat"] is None
    assert COVERAGE["dm"] is None
    assert len(GAPS) == 3


def test_new_topic_mentions_in_team_and_forum(tmp_path):
    fake = FakeRyver()
    fake.team_posts = [post(1, "2026-11-01T00:00:00+00:00", "old", "hello @clara")]
    fake.forum_posts = [post(2, "2026-11-01T00:00:00+00:00", "old forum", "no mention")]
    listener, got = make(tmp_path, fake)
    assert listener.poll_once() == []  # first sight of a room sets the cursor and does not replay history
    fake.team_posts.append(post(3, "2026-11-06T00:00:00+00:00", "check", "please @Clara look"))
    fake.forum_posts.append(post(4, "2026-11-06T01:00:00+00:00", "forum", "@team fyi"))
    fake.forum_posts.append(post(5, "2026-11-06T02:00:00+00:00", "noise", "clara@example.com is not a mention"))
    found = listener.poll_once()
    assert [e.message_id for e in found] == ["post-3", "post-4"]
    assert found[0].kind == "mention" and found[0].source == "Ops topic: check"
    assert found[0].sender == "Carissa" and found[0].org == "jigsawhealth"
    assert found[1].source.startswith("General topic:")
    paths = [path for path, _ in fake.calls]
    assert not any("Chat.History" in p or "postComments" in p or "User.Login" in p or "userNotifications" in p for p in paths)
    assert any(p.startswith("/workrooms(") and "Post.Stream" in p for p in paths)
    assert any(p.startswith("/forums(") and "Post.Stream" in p for p in paths)


def test_own_topic_and_non_mention_skipped(tmp_path):
    fake = FakeRyver()
    listener, got = make(tmp_path, fake)
    listener.poll_once()
    fake.team_posts.append(post(9, "2026-11-06T03:00:00+00:00", "me", "@clara mine", user=7, username="clara"))
    fake.team_posts.append(post(10, "2026-11-06T04:00:00+00:00", "other", "no ping"))
    assert listener.poll_once() == []
    assert got == []


def test_dedupe_within_and_across_polls(tmp_path):
    fake = FakeRyver()
    listener, got = make(tmp_path, fake)
    listener.poll_once()
    mention = post(11, "2026-11-06T05:00:00+00:00", "once", "@clara once")
    fake.team_posts.extend([mention, dict(mention)])
    assert [e.message_id for e in listener.poll_once()] == ["post-11"]
    assert listener.poll_once() == []
    assert [e.message_id for e in got] == ["post-11"]


def test_restart_does_not_repeat_and_catches_the_next_topic(tmp_path):
    fake = FakeRyver()
    listener, got = make(tmp_path, fake)
    listener.poll_once()
    fake.team_posts.append(post(12, "2026-11-06T06:00:00+00:00", "first", "@clara first"))
    listener.poll_once()
    assert [e.message_id for e in got] == ["post-12"]
    restarted, again = make(tmp_path, fake)
    assert restarted.poll_once() == []
    fake.team_posts.append(post(13, "2026-11-06T07:00:00+00:00", "second", "@clara second"))
    assert [e.message_id for e in restarted.poll_once()] == ["post-13"]
    state = json.loads((Path(tmp_path) / "published-seen.json").read_text())
    assert "post-12" in state["seen"] and "post-13" in state["seen"]
    assert "s3cret-value" not in json.dumps(state)


def test_failed_forward_retries_on_the_next_poll(tmp_path):
    fake = FakeRyver()
    cfg = RyverConfig(org="jigsawhealth", username="clara", password="s3cret-value",
                      state_dir=str(tmp_path), listener_mode="rest")
    calls = {"n": 0}

    def flaky(ev):
        calls["n"] += 1
        return calls["n"] > 1

    listener = PublishedAPIListener(cfg, [flaky], fetcher=fake, pause=0, bot_router=None)
    listener.poll_once()
    fake.team_posts.append(post(14, "2026-11-06T08:00:00+00:00", "retry", "@clara retry"))
    assert listener.poll_once() == []
    found = listener.poll_once()
    assert [e.message_id for e in found] == ["post-14"]
    assert calls["n"] == 2


def test_pages_past_a_full_page_so_a_burst_is_not_missed(tmp_path):
    fake = FakeRyver()
    listener, got = make(tmp_path, fake, poll_top=1, max_pages=5)
    fake.team_posts = [post(1, "2026-11-01T00:00:00+00:00", "base", "base")]
    listener.poll_once()
    fake.team_posts.append(post(2, "2026-11-06T00:00:00+00:00", "b", "@clara b"))
    fake.team_posts.append(post(3, "2026-11-06T01:00:00+00:00", "c", "@clara c"))
    found = listener.poll_once()
    assert [e.message_id for e in found] == ["post-2", "post-3"]
    skips = [params.get("$skip") for path, params in fake.calls if "Post.Stream" in path and path.startswith("/workrooms")]
    assert 0 in skips and 1 in skips and 2 in skips


def test_webhook_uses_the_same_bearer_post(tmp_path):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers["Authorization"]
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200); self.end_headers()
        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    fake = FakeRyver()
    cfg = RyverConfig(
        org="jigsawhealth", username="clara", password="s3cret-value", state_dir=str(tmp_path),
        listener_mode="rest", webhook_url=f"http://127.0.0.1:{srv.server_port}/hook", webhook_key="KEY",
    )
    listener = PublishedAPIListener(cfg, fetcher=fake, pause=0, bot_router=None)
    listener.poll_once()
    fake.team_posts.append(post(20, "2026-11-06T09:00:00+00:00", "hook", "@clara hook"))
    found = listener.poll_once()
    assert found and seen["auth"] == "Bearer KEY" and seen["body"]["message_id"] == "post-20"
    assert seen["body"]["kind"] == "mention"
    srv.server_close()


def test_password_is_not_logged(tmp_path, caplog):
    fake = FakeRyver()
    listener, _ = make(tmp_path, fake)
    with caplog.at_level("INFO"):
        listener.poll_once()
    assert "s3cret-value" not in caplog.text
    assert any("published listener gap:" in rec.message for rec in caplog.records)


def test_normalize_stamp_treats_z_and_offset_as_the_same_moment():
    assert normalize_stamp("2026-11-06T00:00:00Z") == normalize_stamp("2026-11-06T00:00:00+00:00")


@responses.activate
def test_http_uses_basic_auth_and_documented_paths_only(tmp_path):
    def body(url):
        if "/users" in url:
            results = [{"id": 7, "username": "clara", "displayName": "Clara"}]
        elif "Post.Stream" in url:
            results = []
        elif "/workrooms" in url:
            results = [{"id": 1, "name": "Ops"}]
        elif "/forums" in url:
            results = [{"id": 2, "name": "General"}]
        else:
            raise AssertionError(url)
        return json.dumps({"d": {"results": results}})

    seen = []

    def cb(request):
        seen.append(request)
        assert request.method == "GET"
        joined = request.url + request.headers.get("Authorization", "")
        assert "User.Login" not in joined and "Chat.History" not in joined
        assert "postComments" not in joined and "userNotifications" not in joined
        assert "s3cret-value" not in request.url
        assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"clara:s3cret-value").decode()
        assert not request.headers["Authorization"].startswith("Session")
        return (200, {}, body(request.url))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API)), callback=cb, content_type="application/json")
    cfg = RyverConfig(org="jigsawhealth", username="clara", password="s3cret-value",
                      state_dir=str(tmp_path), listener_mode="rest", poll_top=50)
    PublishedAPIListener(cfg, fetcher=None, pause=0, bot_router=None).poll_once()
    urls = [r.url for r in seen]
    assert any("/users" in u for u in urls)
    assert any("Post.Stream(archived=false)" in u and "workrooms(1)" in u for u in urls)
    assert any("Post.Stream(archived=false)" in u and "forums(2)" in u for u in urls)
    assert any("orderby" in u and "createDate" in u for u in urls)


@responses.activate
def test_orderby_rejection_falls_back_to_top_and_skip(tmp_path):
    def cb(request):
        if "orderby" in request.url:
            return (400, {}, "no")
        if "/users" in request.url:
            results = [{"id": 7, "username": "clara", "displayName": "Clara"}]
        elif "/workrooms" in request.url and "Post.Stream" not in request.url:
            results = [{"id": 1, "name": "Ops"}]
        elif "/forums" in request.url and "Post.Stream" not in request.url:
            results = []
        else:
            results = []
        return (200, {}, json.dumps({"d": {"results": results}}))

    responses.add_callback(
        responses.GET, re.compile(re.escape(API)), callback=cb, content_type="application/json")
    cfg = RyverConfig(org="jigsawhealth", username="clara", password="s3cret-value",
                      state_dir=str(tmp_path), listener_mode="rest")
    listener = PublishedAPIListener(cfg, pause=0, bot_router=None)
    listener.poll_once()
    assert listener.orderby_ok is False
    assert any("Post.Stream" in c.request.url and "orderby" not in c.request.url for c in responses.calls)


def test_new_install_example_defaults_live_and_has_no_password():
    text = Path(__file__).resolve().parents[1].joinpath("bot.env.example").read_text()
    active = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not any(ln.startswith("RYVER_LISTENER_MODE=") for ln in active)
    assert any(ln.strip().startswith("#") and "RYVER_LISTENER_MODE=rest" in ln for ln in text.splitlines())
    for line in text.splitlines():
        assert not line.startswith("RYVER_PASSWORD=")


def test_build_listener_keeps_live_mode_unless_rest_is_set(tmp_path):
    live_cfg = RyverConfig.from_env({
        "RYVER_ORG": "acme", "RYVER_USER": "quincy", "RYVER_PASSWORD": "x",
        "RYVER_STATE_DIR": str(tmp_path),
    })
    assert isinstance(build_listener(live_cfg, []), RyverListener)
    rest_cfg = RyverConfig.from_env({
        "RYVER_ORG": "acme", "RYVER_USER": "clara", "RYVER_PASSWORD": "x",
        "RYVER_LISTENER_MODE": "published", "RYVER_STATE_DIR": str(tmp_path / "rest"),
    })
    assert isinstance(build_listener(rest_cfg, []), PublishedAPIListener)


def test_rest_refuses_token_only():
    cfg = RyverConfig(org="acme", token="uat-admin", listener_mode="rest", username=None, password=None)
    with pytest.raises(PermissionError):
        PublishedAPIListener(cfg, bot_router=None)


def test_event_shape_matches_the_live_listener():
    ev = Event("mention", "Ops topic: check", 1, "Carissa", "carissa", "@clara", "post-3", "t", "jigsawhealth")
    assert set(ev.to_dict()) == {
        "kind", "source", "source_id", "sender", "sender_username", "text", "message_id", "time", "org",
    }
