import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import manage


def test_app_region_falls_back_within_japan(monkeypatch):
    def usage(*args):
        east = "japaneast" in args[-1]
        return {"value": [{"name": {"value": "*"}, "limit": 0 if east else 30, "currentValue": 0}]}

    monkeypatch.setattr(manage, "az_json", usage)
    assert manage.choose_app_region("example") == "japanwest"


def test_sku_limit_cannot_be_bypassed_by_available_regional_quota(monkeypatch):
    monkeypatch.setattr(
        manage,
        "az_json",
        lambda *args: {
            "value": [
                {"name": {"value": "B1"}, "limit": 0, "currentValue": 0},
                {"name": {"value": "*"}, "limit": 30, "currentValue": 0},
            ]
        },
    )
    with pytest.raises(RuntimeError, match="Request quota"):
        manage.choose_app_region("example")


@pytest.mark.parametrize("prefix", ["repo:owner/repo", "repo:owner@123/repo@456"])
def test_oidc_trust_uses_the_actual_subject_prefix(monkeypatch, prefix):
    monkeypatch.setattr(
        manage,
        "run",
        lambda *args, **kwargs: json.dumps(
            {
                "use_default": True,
                "sub_claim_prefix": prefix,
            }
        ),
    )
    assert manage.github_subject("owner/repo") == prefix + ":ref:refs/heads/main"


def test_custom_oidc_policy_is_not_silently_overridden(monkeypatch):
    monkeypatch.setattr(manage, "run", lambda *args, **kwargs: '{"use_default":false}')
    with pytest.raises(ValueError, match="explicit trust policy"):
        manage.github_subject("owner/repo")


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
