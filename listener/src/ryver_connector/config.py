"""Configuration from environment variables. Never logs secret values."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Optional


class ConfigError(ValueError):
    pass


def _truthy(v: Optional[str]) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _list(v: Optional[str]) -> List[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


@dataclass
class RyverConfig:
    org: str
    username: Optional[str] = None
    password: Optional[str] = field(default=None, repr=False)
    token: Optional[str] = field(default=None, repr=False)   # existing session id
    allow_writes: bool = False
    dry_run: bool = False
    webhook_url: Optional[str] = field(default=None, repr=False)
    webhook_key: Optional[str] = field(default=None, repr=False)
    watch_rooms: List[str] = field(default_factory=list)      # ids or names
    mention_names: List[str] = field(default_factory=list)    # extra aliases
    group_mentions: List[str] = field(default_factory=lambda: ["team", "here", "all"])
    poll_interval: int = 60
    state_dir: str = "./state"
    timezone: str = "UTC"

    @property
    def base_url(self) -> str:
        if self.org.startswith("http"):
            return self.org.rstrip("/")
        host = self.org if "." in self.org else f"{self.org}.ryver.com"
        return f"https://{host}"

    @property
    def api_url(self) -> str:
        return self.base_url + "/api/1/odata.svc"

    @classmethod
    def from_env(cls, env=None) -> "RyverConfig":
        e = os.environ if env is None else env
        org = e.get("RYVER_ORG")
        if not org:
            raise ConfigError("RYVER_ORG is required (e.g. 'acme' for acme.ryver.com)")
        cfg = cls(
            org=org,
            username=e.get("RYVER_USERNAME") or e.get("RYVER_USER"),
            password=e.get("RYVER_PASSWORD"),
            token=e.get("RYVER_TOKEN"),
            allow_writes=_truthy(e.get("RYVER_ALLOW_WRITES")),
            dry_run=_truthy(e.get("RYVER_DRY_RUN")),
            webhook_url=e.get("RYVER_ALERTS_WEBHOOK_URL"),
            webhook_key=e.get("RYVER_ALERTS_WEBHOOK_KEY"),
            watch_rooms=_list(e.get("RYVER_WATCH_ROOMS")),
            mention_names=_list(e.get("RYVER_MENTION_NAMES")),
            poll_interval=int(e.get("RYVER_POLL_INTERVAL", "60")),
            state_dir=e.get("RYVER_STATE_DIR", "./state"),
            timezone=e.get("RYVER_TZ", "UTC"),
        )
        if "RYVER_GROUP_MENTIONS" in e:
            cfg.group_mentions = _list(e.get("RYVER_GROUP_MENTIONS"))
        if not cfg.token and not (cfg.username and cfg.password):
            raise ConfigError("Set RYVER_USER (or RYVER_USERNAME) + RYVER_PASSWORD, or RYVER_TOKEN")
        return cfg
