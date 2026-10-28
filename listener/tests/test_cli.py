from ryver_connector import cli

def test_refuses_writes(monkeypatch, capsys):
    monkeypatch.setenv("RYVER_ORG", "acme"); monkeypatch.setenv("RYVER_TOKEN", "t")
    monkeypatch.delenv("RYVER_ALLOW_WRITES", raising=False)
    assert cli.main(["post", "team", "1", "hi"]) == 3
    assert "disabled" in capsys.readouterr().err

def test_config_error(monkeypatch):
    monkeypatch.delenv("RYVER_ORG", raising=False)
    assert cli.main(["whoami"]) == 2
