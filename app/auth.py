import asyncio

import jwt
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.settings import McpSettings


class ForbiddenCaller(Exception):
    pass


class TokenVerifier:
    def __init__(self, settings: McpSettings, key_client=None):
        self.settings = settings
        self.issuer = f"https://login.microsoftonline.com/{settings.tenant_id}/v2.0"
        self.keys = key_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{settings.tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            timeout=10,
        )

    def verify(self, token: str) -> dict:
        claims = jwt.decode(
            token,
            self.keys.get_signing_key_from_jwt(token).key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.settings.audience,
            options={"require": ["exp", "iat", "iss", "aud", "oid", "tid"]},
            leeway=30,
        )
        caller = claims.get("azp") or claims.get("appid")
        roles = claims.get("roles", [])
        if (
            claims["tid"] != self.settings.tenant_id
            or claims["oid"] != self.settings.caller_object_id
            or caller != self.settings.caller_id
            or not isinstance(roles, list)
            or "Mcp.Invoke" not in roles
        ):
            raise ForbiddenCaller
        return claims


class McpAuthentication:
    """Pure ASGI middleware: do not buffer or disrupt MCP response streams."""

    def __init__(self, app, verifier: TokenVerifier):
        self.app = app
        self.verifier = verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        header = Headers(scope=scope).get("authorization", "")
        scheme, _, token = header.partition(" ")
        try:
            if scheme.lower() != "bearer" or not token:
                raise jwt.InvalidTokenError
            await asyncio.to_thread(self.verifier.verify, token)
        except ForbiddenCaller:
            response = JSONResponse({"detail": "Caller is not permitted"}, status_code=403)
        except (jwt.InvalidTokenError, jwt.PyJWKClientError):
            response = JSONResponse(
                {"detail": "A valid MCP access token is required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            return await self.app(scope, receive, send)
        await response(scope, receive, send)
