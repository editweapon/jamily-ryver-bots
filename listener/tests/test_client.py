import json
import pytest
import responses
from ryver_connector import RyverClient, WritesDisabledError, RyverAPIError

API = "https://acme.ryver.com/api/1/odata.svc"

def _login(rsps):
    rsps.add(responses.POST, f"{API}/User.Login(client='pyryver')",
             json={"d": {"id": 7, "sessionId": "SID", "services": {"chat": "wss://x/ws"}}})

@responses.activate
def test_whoami(cfg):
    _login(responses)
    responses.add(responses.GET, f"{API}/users", json={"d": {"results": [{"id": 7, "username": "bot"}]}})
    c = RyverClient(cfg)
    assert c.whoami()["username"] == "bot"
    assert responses.calls[1].request.headers["Authorization"] == "Session SID"
    assert "Basic" in responses.calls[0].request.headers["Authorization"]

@responses.activate
def test_login_fail(cfg):
    responses.add(responses.POST, f"{API}/User.Login(client='pyryver')", status=401)
    with pytest.raises(RyverAPIError):
        RyverClient(cfg).login()

@responses.activate
def test_user_pagination(cfg):
    _login(responses)
    page = [{"id": i} for i in range(500)]
    responses.add(responses.GET, f"{API}/users", json={"d": {"results": page}})
    responses.add(responses.GET, f"{API}/users", json={"d": {"results": [{"id": 999}]}})
    users = RyverClient(cfg).list_users()
    assert len(users) == 501
    assert "%24skip=500" in responses.calls[2].request.url

@responses.activate
def test_reads(cfg):
    _login(responses)
    responses.add(responses.GET, f"{API}/workrooms(5)/Post.Stream()", json={"d": {"results": [{"id": 1}]}})
    responses.add(responses.GET, f"{API}/postComments", json={"d": {"results": [{"id": 2}]}})
    responses.add(responses.GET, f"{API}/users(9)/Chat.History()", json={"d": {"results": [{"id": "m"}]}})
    c = RyverClient(cfg)
    assert c.list_topics("team", 5)[0]["id"] == 1
    assert c.topic_comments(1)[0]["id"] == 2
    assert "post%2Fid+eq+1" in responses.calls[2].request.url
    assert c.dm_history(9)[0]["id"] == "m"

def test_writes_disabled(cfg):
    c = RyverClient(cfg)
    for f in (lambda: c.send_message("team", 1, "x"), lambda: c.comment_on_topic(1, "x"),
              lambda: c.post_topic("forum", 1, "s", "b"), lambda: c.react("team", 1, "m", ":+1:")):
        with pytest.raises(WritesDisabledError):
            f()

@responses.activate
def test_dry_run_sends_nothing(cfg):
    cfg.allow_writes = True; cfg.dry_run = True
    _login(responses)
    r = RyverClient(cfg).comment_on_topic(42, "hello")
    assert r["dry_run"] and r["payload"] == {"post": {"id": 42}, "comment": "hello"}
    assert all(c.request.method != "POST" or "Login" in c.request.url for c in responses.calls)

@responses.activate
def test_real_writes(cfg):
    cfg.allow_writes = True
    _login(responses)
    responses.add(responses.POST, f"{API}/postComments", json={"d": {"id": 1}})
    responses.add(responses.POST, f"{API}/forums(3)/Chat.PostMessage()", json={"d": {"id": "abc"}})
    responses.add(responses.POST, f"{API}/posts", json={"d": {"id": 2}})
    c = RyverClient(cfg)
    c.comment_on_topic(42, "hi")
    assert json.loads(responses.calls[1].request.body) == {"post": {"id": 42}, "comment": "hi"}
    c.send_message("forum", 3, "yo")
    assert json.loads(responses.calls[2].request.body) == {"body": "yo"}
    c.post_topic("team", 5, "S", "B")
    b = json.loads(responses.calls[3].request.body)
    assert b["outAssociations"]["results"][0] == {"inSecured": True, "inType": "Entity.Workroom", "inId": 5}

def test_bad_kind(cfg):
    cfg.allow_writes = True
    with pytest.raises(ValueError):
        RyverClient(cfg).send_message("planet", 1, "x")
