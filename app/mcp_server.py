from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from app.auth import McpAuthentication, TokenVerifier
from app.settings import McpSettings

PRODUCTS = (
    {
        "product_id": "PC001",
        "name": "軽量ノートPC",
        "category": "PC",
        "price_jpy": 98000,
        "stock": 12,
    },
    {
        "product_id": "PC002",
        "name": "開発用ノートPC",
        "category": "PC",
        "price_jpy": 168000,
        "stock": 3,
    },
    {
        "product_id": "KB001",
        "name": "静音キーボード",
        "category": "周辺機器",
        "price_jpy": 6800,
        "stock": 25,
    },
    {
        "product_id": "MS001",
        "name": "ワイヤレスマウス",
        "category": "周辺機器",
        "price_jpy": 3200,
        "stock": 0,
    },
)


class ProductInfo(BaseModel):
    product_id: str
    name: str
    category: str
    price_jpy: int


class InventoryResult(BaseModel):
    product_id: str
    found: bool
    name: str | None = None
    stock: int | None = None


def build_server() -> MCPServer:
    server = MCPServer("demo-inventory")
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=read_only, structured_output=True)
    def search_products(
        keyword: Annotated[str, Field(min_length=1, max_length=100)],
    ) -> list[ProductInfo]:
        """架空の商品を名前・カテゴリ・商品IDで検索する。在庫数はget_inventoryで照会する。"""
        term = keyword.strip().casefold()
        if not term:
            return []
        return [
            ProductInfo.model_validate(product)
            for product in PRODUCTS
            if any(
                term in str(product[key]).casefold() for key in ("name", "category", "product_id")
            )
        ]

    @server.tool(annotations=read_only, structured_output=True)
    def get_inventory(
        product_id: Annotated[str, Field(pattern=r"^[A-Z]{2}[0-9]{3}$")],
    ) -> InventoryResult:
        """商品IDに対する架空の在庫数を返す。商品が存在しないときはfound=false。"""
        for product in PRODUCTS:
            if product["product_id"] == product_id:
                return InventoryResult(
                    **{
                        "product_id": product_id,
                        "name": product["name"],
                        "stock": product["stock"],
                        "found": True,
                    }
                )
        return InventoryResult(product_id=product_id, found=False)

    return server


def create_app(settings: McpSettings | None = None, verifier=None) -> FastAPI:
    settings = settings or McpSettings.from_env()
    server = build_server()
    allowed_hosts = [settings.hostname, f"{settings.hostname}:*"]
    if settings.local:
        allowed_hosts.extend(["localhost:*", "127.0.0.1:*", "testserver"])
    mcp_app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=32768,
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts, allowed_origins=[]
        ),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.mount("/", mcp_app)
    if not settings.local:
        app.add_middleware(McpAuthentication, verifier=verifier or TokenVerifier(settings))
    return app
