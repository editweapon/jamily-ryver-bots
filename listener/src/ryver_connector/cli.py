"""ryver-connector CLI: whoami | users | teams | forums | topics | comments | history | listen | post | comment | topic | react"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os
import sys

from .config import ConfigError, RyverConfig
from .client import RyverClient, WritesDisabledError, RyverAPIError
from .listener import RyverListener


def _out(x):
    print(json.dumps(x, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ryver-connector")
    p.add_argument("--dry-run", action="store_true", help="never send writes; print them instead")
    p.add_argument("-v", "--verbose", action="store_true")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("whoami")
    s.add_parser("users"); s.add_parser("teams"); s.add_parser("forums")
    t = s.add_parser("topics"); t.add_argument("kind"); t.add_argument("id", type=int); t.add_argument("--top", type=int, default=20)
    c = s.add_parser("comments"); c.add_argument("post_id", type=int)
    h = s.add_parser("history"); h.add_argument("kind", help="forum|team|dm"); h.add_argument("id", type=int); h.add_argument("--top", type=int, default=20)
    l = s.add_parser("listen"); l.add_argument("--jsonl", help="also append events to this file"); l.add_argument("--no-poll", action="store_true")
    l.add_argument("--print", action="store_true", help="print events to stdout")
    m = s.add_parser("post", help="send chat message"); m.add_argument("kind"); m.add_argument("id", type=int); m.add_argument("text")
    cm = s.add_parser("comment", help="comment on topic"); cm.add_argument("post_id", type=int); cm.add_argument("text")
    tp = s.add_parser("topic", help="create topic"); tp.add_argument("kind"); tp.add_argument("id", type=int); tp.add_argument("subject"); tp.add_argument("body")
    r = s.add_parser("react"); r.add_argument("kind"); r.add_argument("id", type=int); r.add_argument("message_id"); r.add_argument("emoji")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    try:
        cfg = RyverConfig.from_env()
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr); return 2
    if a.dry_run:
        cfg.dry_run = True
    try:
        if a.cmd == "listen":
            cbs = [lambda ev: print(json.dumps(ev.to_dict()), flush=True)] if a.print else []
            asyncio.run(RyverListener(cfg, cbs, jsonl_path=a.jsonl, poll_topics=not a.no_poll).run())
            return 0
        c = RyverClient(cfg)
        cmds = {
            "whoami": lambda: c.whoami(),
            "users": c.list_users, "teams": c.list_teams, "forums": c.list_forums,
            "topics": lambda: c.list_topics(a.kind, a.id, a.top),
            "comments": lambda: c.topic_comments(a.post_id),
            "history": lambda: c.chat_history(a.kind, a.id, a.top),
            "post": lambda: c.send_message(a.kind, a.id, a.text),
            "comment": lambda: c.comment_on_topic(a.post_id, a.text),
            "topic": lambda: c.post_topic(a.kind, a.id, a.subject, a.body),
            "react": lambda: c.react(a.kind, a.id, a.message_id, a.emoji),
        }
        _out(cmds[a.cmd]())
        return 0
    except WritesDisabledError as e:
        print(f"refused: {e}", file=sys.stderr); return 3
    except RyverAPIError as e:
        print(f"api error: {e}", file=sys.stderr); return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
