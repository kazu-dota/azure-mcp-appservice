"""Bootstrap locally; deploy and clean up using the same commands in GitHub Actions."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
WORKLOAD = ROOT / "infra/workload"
LOCAL.mkdir(exist_ok=True)


def executable(name):
    suffix = ".exe" if os.name == "nt" else ""
    candidate = ROOT / ".tools" / name / (name + suffix)
    if name == "az" and (ROOT / ".tools/azure-cli/Scripts/az.bat").exists():
        scripts = ROOT / ".tools/azure-cli/Scripts"
        os.environ["PATH"] = str(scripts) + os.pathsep + os.environ["PATH"]
        return str(scripts / "az.bat")
    return str(candidate) if candidate.exists() else (shutil.which(name) or name)


def run(name, *args, capture=False, check=True, input_text=None):
    result = subprocess.run(
        [executable(name), *map(str, args)],
        cwd=ROOT,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        stdout=subprocess.PIPE if capture else None,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    return result.stdout.strip() if capture else result.returncode


def az_json(*args):
    return json.loads(run("az", *args, "-o", "json", capture=True))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def config():
    text = os.getenv("AZURE_CONFIG") or (LOCAL / "azure-config.json").read_text(encoding="utf-8")
    data = json.loads(text)
    prefix = data["prefix"]
    if not re.fullmatch(r"azmcp[a-z0-9]{6}", prefix):
        raise ValueError("Unexpected environment prefix")
    for key, expected in {
        "resource_group_name": f"{prefix}-workload",
        "bootstrap_group_name": f"{prefix}-bootstrap",
        "state_account": f"{prefix}state",
    }.items():
        if data[key] != expected:
            raise ValueError(f"Unexpected {key}")
    if data["location"] not in ("japaneast", "japanwest"):
        raise ValueError("A Japanese Azure region is required")
    datetime.fromisoformat(data["expires_at"])
    return data


def terraform(*args, bootstrap=False, capture=False):
    directory = ROOT / "infra/bootstrap" if bootstrap else WORKLOAD
    return run("terraform", f"-chdir={directory}", *args, capture=capture)


def prepare(data, cleanup=False):
    write_json(LOCAL / "workload.tfvars.json", {"config": data})
    backend = {
        "resource_group_name": data["bootstrap_group_name"],
        "storage_account_name": data["state_account"],
        "container_name": "tfstate",
        "key": "workload.tfstate",
        "subscription_id": data["subscription_id"],
        "tenant_id": data["tenant_id"],
        "use_azuread_auth": True,
    }
    write_json(LOCAL / "backend.json", backend)
    active = datetime.now(UTC) < datetime.fromisoformat(data["expires_at"])
    due = not active
    if cleanup and os.getenv("CLEANUP_NOW") == "true":
        if os.getenv("CONFIRM_PREFIX") != data["prefix"]:
            raise ValueError("Manual cleanup requires the exact environment prefix")
        due = True
    if os.getenv("GITHUB_ACTIONS"):
        for key, value in data.items():
            if key.endswith(("_id", "_identity_id")):
                print(f"::add-mask::{value}", flush=True)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"active={str(active).lower()}\ndue={str(due).lower()}\n")
    print(f"Environment: {data['prefix']}; expires: {data['expires_at']}", flush=True)
    return active


def init_workload():
    terraform("init", "-input=false", f"-backend-config={LOCAL / 'backend.json'}")


def bootstrap(repository):
    values_path = LOCAL / "bootstrap.tfvars.json"
    if values_path.exists():
        values = json.loads(values_path.read_text(encoding="utf-8"))
        if values["repository"] != repository:
            raise ValueError("Existing bootstrap belongs to a different GitHub repository")
        if datetime.now(UTC) >= datetime.fromisoformat(values["expires_at"]):
            raise ValueError("This environment has expired; clean it up before creating another")
    else:
        account = az_json("account", "show")
        values = {
            "subscription_id": account["id"],
            "tenant_id": account["tenantId"],
            "prefix": "azmcp" + uuid.uuid4().hex[:6],
            "location": "japaneast",
            "repository": repository,
            "expires_at": (datetime.now(UTC) + timedelta(hours=48)).isoformat(timespec="seconds"),
        }
        write_json(values_path, values)
    print(f"Bootstrap environment: {values['prefix']}", flush=True)
    for namespace in (
        "Microsoft.Web",
        "Microsoft.Network",
        "Microsoft.CognitiveServices",
        "Microsoft.Storage",
        "Microsoft.ContainerRegistry",
        "Microsoft.ManagedIdentity",
    ):
        print(f"Registering provider: {namespace}", flush=True)
        state = run(
            "az",
            "provider",
            "show",
            "--namespace",
            namespace,
            "--query",
            "registrationState",
            "-o",
            "tsv",
            capture=True,
        )
        if state != "Registered":
            run("az", "provider", "register", "--namespace", namespace, "--wait", "-o", "none")
    terraform("init", "-input=false", bootstrap=True)
    plan = LOCAL / "bootstrap.tfplan"
    terraform("plan", "-input=false", f"-var-file={values_path}", f"-out={plan}", bootstrap=True)
    terraform("apply", "-input=false", str(plan), bootstrap=True)
    data = json.loads(terraform("output", "-json", "config", bootstrap=True, capture=True))
    write_json(LOCAL / "azure-config.json", data)
    run(
        "gh",
        "variable",
        "set",
        "AZURE_CONFIG",
        "--repo",
        repository,
        input_text=json.dumps(data),
    )
    for name, key in (
        ("AZURE_CLIENT_ID", "deployer_client_id"),
        ("AZURE_TENANT_ID", "tenant_id"),
        ("AZURE_SUBSCRIPTION_ID", "subscription_id"),
    ):
        run("gh", "variable", "set", name, "--repo", repository, "--body", data[key])
    print("Bootstrap complete. GitHub Actions can now deploy using OIDC.", flush=True)


def deploy(data):
    if not prepare(data):
        raise RuntimeError("Deployment refused: the environment has expired")
    init_workload()
    tag = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", tag):
        raise ValueError("An immutable Git commit SHA is required for the image tag")
    plan = LOCAL / "workload.tfplan"
    terraform(
        "plan",
        "-input=false",
        f"-var-file={LOCAL / 'workload.tfvars.json'}",
        f"-var=image_tag={tag}",
        f"-out={plan}",
    )
    terraform("apply", "-input=false", str(plan))
    outputs = json.loads(terraform("output", "-json", capture=True))
    registry = outputs["registry_name"]["value"]
    run("az", "acr", "login", "--name", registry)
    image = outputs["registry_server"]["value"] + "/demo:" + tag
    run("docker", "build", "--pull", "--tag", image, ".")
    run("docker", "push", image)
    for suffix in ("mcp", "front"):
        run(
            "az",
            "webapp",
            "restart",
            "--resource-group",
            data["resource_group_name"],
            "--name",
            f"{data['prefix']}-{suffix}",
        )
    write_json(LOCAL / "outputs.json", {k: v["value"] for k, v in outputs.items()})


def verify_group(data, name):
    exists = run("az", "group", "exists", "--name", name, capture=True) == "true"
    if exists:
        group = az_json("group", "show", "--name", name)
        tags = group.get("tags") or {}
        if tags.get("project") != data["prefix"] or tags.get("purpose") != "azure-mcp-demo":
            raise RuntimeError("Refusing to delete a group without the expected ownership tags")
    return exists


def cleanup(data):
    prepare(data, cleanup=True)
    if datetime.now(UTC) < datetime.fromisoformat(data["expires_at"]):
        if os.getenv("CLEANUP_NOW") != "true" or os.getenv("CONFIRM_PREFIX") != data["prefix"]:
            raise RuntimeError("The environment has not expired")
    groups = [data["resource_group_name"], data["bootstrap_group_name"]]
    existing = {name: verify_group(data, name) for name in groups}
    destroyed = False
    if existing[data["bootstrap_group_name"]]:
        try:
            init_workload()
            terraform(
                "destroy",
                "-auto-approve",
                "-input=false",
                f"-var-file={LOCAL / 'workload.tfvars.json'}",
            )
            destroyed = True
        except subprocess.CalledProcessError:
            print(
                "Terraform destroy failed; removing only the verified, tagged demo groups.",
                flush=True,
            )
    for key, suffix in (("frontend_application_id", "frontend"), ("mcp_application_id", "mcp")):
        object_id = data[key]
        app_text = run(
            "az", "ad", "app", "show", "--id", object_id, "-o", "json", capture=True, check=False
        )
        if app_text:
            application = json.loads(app_text)
            if application["displayName"] != f"{data['prefix']}-{suffix}":
                raise RuntimeError("Refusing to delete an unexpected Entra application")
            run("az", "ad", "app", "delete", "--id", object_id)
    for name in groups:
        if existing[name]:
            run("az", "group", "delete", "--name", name, "--yes")
        if run("az", "group", "exists", "--name", name, capture=True) != "false":
            raise RuntimeError("Resource group deletion is incomplete")
    evidence = {
        "checked_at": datetime.now(UTC).isoformat(),
        "terraform_destroy": destroyed,
        "workload_group_deleted": True,
        "bootstrap_group_deleted": True,
        "entra_applications_deleted": True,
    }
    write_json(LOCAL / "cleanup-result.json", evidence)
    if repository := os.getenv("GITHUB_REPOSITORY"):
        for workflow in ("deploy.yml", "cleanup.yml"):
            run(
                "gh",
                "api",
                "--method",
                "PUT",
                f"repos/{repository}/actions/workflows/{workflow}/disable",
            )
    print(json.dumps(evidence), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("bootstrap", "prepare", "deploy", "cleanup"))
    parser.add_argument("--repository")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.command == "bootstrap":
        if not args.repository or not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repository):
            parser.error("--repository OWNER/NAME is required")
        bootstrap(args.repository)
    elif args.command == "prepare":
        prepare(config(), cleanup=args.cleanup)
    elif args.command == "deploy":
        deploy(config())
    else:
        cleanup(config())


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Command failed with exit code {exc.returncode}")
