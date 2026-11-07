import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import manage


def test_invalid_prefix_cannot_select_a_different_environment(monkeypatch):
    monkeypatch.setenv("AZURE_CONFIG", json.dumps({"prefix": "production"}))
    with pytest.raises(ValueError, match="prefix"):
        manage.config()


def test_cleanup_refuses_a_group_without_ownership_tags(monkeypatch):
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        return "true"

    monkeypatch.setattr(manage, "run", fake_run)
    monkeypatch.setattr(manage, "az_json", lambda *args: {"tags": {"project": "another-app"}})
    with pytest.raises(RuntimeError, match="ownership tags"):
        manage.verify_group({"prefix": "azmcpabc123"}, "azmcpabc123-workload")
    assert not any("delete" in command for command in commands)


def test_manual_cleanup_requires_exact_prefix(monkeypatch, tmp_path):
    monkeypatch.setattr(manage, "LOCAL", tmp_path)
    monkeypatch.setenv("CLEANUP_NOW", "true")
    monkeypatch.setenv("CONFIRM_PREFIX", "wrong-environment")
    data = {
        "prefix": "azmcpabc123",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "bootstrap_group_name": "azmcpabc123-bootstrap",
        "state_account": "azmcpabc123state",
        "subscription_id": "example",
        "tenant_id": "example",
    }
    with pytest.raises(ValueError, match="exact environment prefix"):
        manage.prepare(data, cleanup=True)
