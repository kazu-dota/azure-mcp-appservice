"""Public checks plus results of probes executed under the real frontend identity."""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from manage import LOCAL, az_json, config, terraform, write_json


def main():
    data = config()
    outputs = json.loads((LOCAL / "outputs.json").read_text(encoding="utf-8"))
    with httpx.Client(timeout=20, follow_redirects=False) as http:
        for attempt in range(60):
            try:
                response = http.get(outputs["frontend_url"] + "/health")
                health = response.json()
                if (
                    response.status_code == 200
                    and health.get("ready")
                    and health.get("version") == os.environ["GITHUB_SHA"]
                ):
                    break
            except (httpx.HTTPError, ValueError):
                pass
            print(f"Waiting for deployment readiness ({attempt + 1}/60)", flush=True)
            time.sleep(10)
        else:
            raise RuntimeError("The new frontend did not pass its private-service startup checks")
        if not health.get("checks") or not all(health["checks"].values()):
            raise RuntimeError("Private-service checks are incomplete")
        response = http.get(outputs["frontend_url"] + "/")
        assert response.status_code in (302, 307), "Frontend did not require sign-in"
        assert "/.auth/login/aad" in response.headers.get("location", "")
        frontend_requires_login = True
        response = http.post(outputs["mcp_url"], json={})
        assert response.status_code == 403, "MCP public network access was not denied"
    mcp = az_json(
        "webapp",
        "show",
        "--name",
        data["prefix"] + "-mcp",
        "--resource-group",
        data["resource_group_name"],
    )
    assert mcp["publicNetworkAccess"] == "Disabled"
    foundry = az_json(
        "cognitiveservices",
        "account",
        "show",
        "--name",
        outputs["foundry_name"],
        "--resource-group",
        data["resource_group_name"],
    )
    assert foundry["properties"]["publicNetworkAccess"] == "Disabled"
    assert foundry["properties"]["disableLocalAuth"] is True
    # A fresh plan must not propose a change to the deployed image or configuration.
    terraform(
        "plan",
        "-input=false",
        "-detailed-exitcode",
        f"-var-file={LOCAL / 'workload.tfvars.json'}",
        f"-var=image_tag={os.environ['GITHUB_SHA']}",
    )
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "commit": os.environ["GITHUB_SHA"],
        "frontend_requires_login": frontend_requires_login,
        "mcp_public_access_denied": True,
        "foundry_public_access_disabled": True,
        "foundry_key_auth_disabled": True,
        "private_startup_checks": health["checks"],
        "terraform_no_changes": True,
        "interactive_login_verified": False,
    }
    evidence = Path("docs/evidence")
    evidence.mkdir(exist_ok=True)
    write_json(evidence / "deployment-checks.json", result)
    print(json.dumps(result, indent=2), flush=True)
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write(
                "### Deployment checks passed\n\n```json\n"
                + json.dumps(result, indent=2)
                + "\n```\n"
            )


if __name__ == "__main__":
    main()
