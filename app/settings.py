import os
from dataclasses import dataclass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing setting: {name}")
    return value


def local_mode() -> bool:
    local = os.getenv("APP_ENV") == "local"
    if local and os.getenv("WEBSITE_SITE_NAME"):
        raise RuntimeError("Local authentication bypass is forbidden on App Service")
    return local


@dataclass(frozen=True)
class McpSettings:
    local: bool
    hostname: str
    tenant_id: str = ""
    audience: str = ""
    caller_id: str = ""
    caller_object_id: str = ""

    @classmethod
    def from_env(cls):
        local = local_mode()
        return cls(
            local=local,
            hostname=os.getenv("WEBSITE_HOSTNAME", os.getenv("MCP_HOSTNAME", "127.0.0.1")),
            **(
                {}
                if local
                else {
                    "tenant_id": required("AZURE_TENANT_ID"),
                    "audience": required("MCP_AUDIENCE"),
                    "caller_id": required("FRONTEND_CLIENT_ID"),
                    "caller_object_id": required("FRONTEND_OBJECT_ID"),
                }
            ),
        )


@dataclass(frozen=True)
class FrontendSettings:
    local: bool
    mcp_url: str
    foundry_endpoint: str
    deployment: str
    origin: str
    operator_id: str = ""
    identity_client_id: str = ""
    mcp_scope: str = ""
    version: str = "local"

    @classmethod
    def from_env(cls):
        local = local_mode()
        return cls(
            local=local,
            mcp_url=required("MCP_URL"),
            foundry_endpoint=required("FOUNDRY_ENDPOINT").rstrip("/"),
            deployment=os.getenv("MODEL_DEPLOYMENT", "gpt-4.1-mini"),
            origin=(
                f"https://{os.environ['WEBSITE_HOSTNAME']}"
                if os.getenv("WEBSITE_HOSTNAME")
                else os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:8000")
            ).rstrip("/"),
            version=os.getenv("APP_VERSION", "local"),
            **(
                {}
                if local
                else {
                    "operator_id": required("OPERATOR_OBJECT_ID"),
                    "identity_client_id": required("AZURE_CLIENT_ID"),
                    "mcp_scope": required("MCP_SCOPE"),
                }
            ),
        )
