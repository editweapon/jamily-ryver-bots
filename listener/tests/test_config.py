import pytest
from ryver_connector import RyverConfig, ConfigError

def test_from_env_defaults():
    c = RyverConfig.from_env({"RYVER_ORG": "acme", "RYVER_USERNAME": "b", "RYVER_PASSWORD": "s3cret",
                              "RYVER_WATCH_ROOMS": "Ops, 12"})
    assert c.api_url == "https://acme.ryver.com/api/1/odata.svc"
    assert not c.allow_writes and c.watch_rooms == ["Ops", "12"]
    assert c.listener_mode == "live" and c.poll_interval == 60 and c.poll_top == 50
    assert "s3cret" not in repr(c)

def test_full_host_and_flags():
    c = RyverConfig.from_env({"RYVER_ORG": "chat.example.com", "RYVER_TOKEN": "t",
                              "RYVER_ALLOW_WRITES": "1", "RYVER_DRY_RUN": "true", "RYVER_GROUP_MENTIONS": ""})
    assert c.base_url == "https://chat.example.com" and c.allow_writes and c.dry_run and c.group_mentions == []

@pytest.mark.parametrize("env", [{}, {"RYVER_ORG": "a"}, {"RYVER_ORG": "a", "RYVER_USERNAME": "b"}])
def test_missing(env):
    with pytest.raises(ConfigError):
        RyverConfig.from_env(env)

def test_listener_mode_blank_or_websocket_stays_live():
    base = {"RYVER_ORG": "acme", "RYVER_USER": "quincy", "RYVER_PASSWORD": "x"}
    assert RyverConfig.from_env(base).listener_mode == "live"
    assert RyverConfig.from_env({**base, "RYVER_LISTENER_MODE": "  "}).listener_mode == "live"
    assert RyverConfig.from_env({**base, "RYVER_LISTENER_MODE": "websocket"}).listener_mode == "live"
    assert RyverConfig.from_env({**base, "RYVER_LISTENER_MODE": "rest"}).listener_mode == "rest"
    with pytest.raises(ConfigError):
        RyverConfig.from_env({**base, "RYVER_LISTENER_MODE": "admin"})
