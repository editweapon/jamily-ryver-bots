#!/usr/bin/env python3
"""ryver.py - tiny Ryver REST (OData v1) client and CLI for Jamily bots.

Stdlib only. Config from env vars or a local .env file (never committed):
  RYVER_ORG       org subdomain (default: jigsawhealth)
  RYVER_TOKEN     Bearer token from a Custom Integration (preferred), or
  RYVER_USER / RYVER_PASSWORD  for Basic auth.

Endpoint status (see README):
  VERIFIED   = shown in https://api.ryver.com/ryvrest_api_examples.html
  UNVERIFIED = inferred from community clients / the web client; may change.
"""
import argparse, base64, json, os, sys, urllib.error, urllib.parse, urllib.request

__version__ = "0.1.0"


def load_env(path=".env"):
    """Load KEY=VALUE lines from .env into os.environ (env vars win)."""
    for p in (path, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
        if os.path.isfile(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


class RyverError(Exception):
    pass


class Ryver:
    def __init__(self, org=None, user=None, password=None, token=None):
        self.org = org or os.environ.get("RYVER_ORG", "jigsawhealth")
        self.user = user or os.environ.get("RYVER_USER")
        self.password = password or os.environ.get("RYVER_PASSWORD")
        self.token = token or os.environ.get("RYVER_TOKEN")
        self.base = "https://%s.ryver.com/api/1/odata.svc" % self.org

    def _auth(self):
        if self.token:
            return "Bearer " + self.token
        if self.user and self.password:
            raw = ("%s:%s" % (self.user, self.password)).encode()
            return "Basic " + base64.b64encode(raw).decode()
        raise RyverError("No credentials: set RYVER_TOKEN or RYVER_USER + RYVER_PASSWORD")

    def request(self, method, path, body=None, params=None):
        url = self.base + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe="$(),=/'")
        headers = {"Accept": "application/json", "Authorization": self._auth()}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                txt = r.read().decode()
        except urllib.error.HTTPError as e:
            raise RyverError("HTTP %s %s: %s" % (e.code, url, e.read().decode()[:500]))
        out = json.loads(txt) if txt else {}
        d = out.get("d", out) if isinstance(out, dict) else out
        return d.get("results", d) if isinstance(d, dict) else d

    # ---- reads ----
    def whoami(self):
        # UNVERIFIED: Ryver.Info() is what the web client and community libs
        # (e.g. pyryver) call at startup; it returns the signed-in user under "me".
        info = self.request("GET", "/Ryver.Info()")
        return info.get("me", info) if isinstance(info, dict) else info

    def list_teams(self):
        # VERIFIED: GET /workrooms
        return self.request("GET", "/workrooms", params={"$select": "id,name,nickname", "$top": "200"})

    def list_forums(self):
        # VERIFIED: GET /forums
        return self.request("GET", "/forums", params={"$select": "id,name,nickname", "$top": "200"})

    def list_topics(self, team_id, forum=False, top=25):
        # VERIFIED: GET /workrooms(ID)/Post.Stream(archived=false)
        ent = "forums" if forum else "workrooms"
        return self.request("GET", "/%s(%d)/Post.Stream(archived=false)" % (ent, int(team_id)),
                            params={"$format": "json", "$top": str(top)})

    def find_user(self, username):
        # VERIFIED: GET /users ; $filter by username is standard OData (UNVERIFIED filter support)
        res = self.request("GET", "/users", params={"$filter": "username eq '%s'" % username.replace("'", "''"),
                                                     "$select": "id,username,displayName"})
        if not res:
            raise RyverError("user not found: " + username)
        return res[0]

    def mentions(self, top=25):
        # UNVERIFIED: /userNotifications is used by the web client / pyryver for the
        # signed-in user's notification feed (mentions, replies). Read only; this
        # never marks anything read.
        return self.request("GET", "/userNotifications",
                            params={"$format": "json", "$top": str(top), "$orderby": "modifyDate desc"})

    # ---- writes ----
    def create_topic(self, team_id, subject, body, forum=False):
        # VERIFIED: POST /posts with outAssociations (recordType "note")
        return self.request("POST", "/posts", body={
            "subject": subject, "body": body, "recordType": "note",
            "outAssociations": {"results": [{"inSecured": True,
                                             "inType": "Entity.Forum" if forum else "Entity.Workroom",
                                             "inId": int(team_id)}]}})

    def reply_topic(self, topic_id, body):
        # UNVERIFIED: POST /postComments with post.id, as used by the web client / pyryver.
        return self.request("POST", "/postComments", body={"comment": body, "post": {"id": int(topic_id)}})

    def send_dm(self, username, body):
        # Chat.PostMessage is VERIFIED for workrooms/forums; the users(ID) variant
        # for DMs is UNVERIFIED (used by pyryver and the web client).
        uid = self.find_user(username)["id"]
        return self.request("POST", "/users(%d)/Chat.PostMessage()" % int(uid), body={"body": body})


def main(argv=None):
    load_env()
    p = argparse.ArgumentParser(prog="ryver.py", description="Ryver REST CLI for Jamily bots (v%s)" % __version__)
    p.add_argument("--version", action="version", version=__version__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("whoami", help="show signed-in user [unverified endpoint]")
    s.add_parser("teams", help="list teams")
    s.add_parser("forums", help="list forums")
    t = s.add_parser("topics", help="list topics in a team"); t.add_argument("team_id", type=int)
    t.add_argument("--forum", action="store_true"); t.add_argument("--top", type=int, default=25)
    c = s.add_parser("create-topic", help="create a Topic in a team")
    c.add_argument("team_id", type=int); c.add_argument("subject"); c.add_argument("body")
    c.add_argument("--forum", action="store_true")
    r = s.add_parser("reply", help="reply to a Topic [unverified endpoint]")
    r.add_argument("topic_id", type=int); r.add_argument("body")
    d = s.add_parser("dm", help="DM a user by username [unverified endpoint]")
    d.add_argument("username"); d.add_argument("body")
    m = s.add_parser("mentions", help="recent notifications/@mentions [unverified endpoint]")
    m.add_argument("--top", type=int, default=25)
    a = p.parse_args(argv)
    rv = Ryver()
    try:
        out = {"whoami": lambda: rv.whoami(), "teams": rv.list_teams, "forums": rv.list_forums,
               "topics": lambda: rv.list_topics(a.team_id, a.forum, a.top),
               "create-topic": lambda: rv.create_topic(a.team_id, a.subject, a.body, a.forum),
               "reply": lambda: rv.reply_topic(a.topic_id, a.body),
               "dm": lambda: rv.send_dm(a.username, a.body),
               "mentions": lambda: rv.mentions(a.top)}[a.cmd]()
    except RyverError as e:
        print("error: %s" % e, file=sys.stderr); return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
