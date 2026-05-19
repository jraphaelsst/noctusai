"""waha.server.* tools — instance health/version.

All PURE reads. `waha.server.ping` hits the **unauthenticated**
`/ping` (the "is the host up at all" signal, independent of the API
key — the exact disambiguation the WAHA dashboard's conflated
"not connected / wrong key" error needs).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    ServerPingInput,
    ServerPingOutput,
    ServerStatusInput,
    ServerStatusOutput,
    ServerVersionInput,
    ServerVersionOutput,
)

logger = logging.getLogger(__name__)


def _ctx(require_auth: bool = True) -> dict:
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
        "require_auth": require_auth,
    }


async def server_version(args: dict) -> dict:
    ServerVersionInput(**args)
    try:
        data = api.request_json("GET", "/api/server/version", **_ctx())
    except api.WahaApiError as e:
        return ServerVersionOutput(error=typed_error(e)).model_dump()
    return ServerVersionOutput(
        version=data if isinstance(data, dict) else {"value": data}
    ).model_dump()


async def server_status(args: dict) -> dict:
    ServerStatusInput(**args)
    try:
        data = api.request_json("GET", "/api/server/status", **_ctx())
    except api.WahaApiError as e:
        return ServerStatusOutput(error=typed_error(e)).model_dump()
    return ServerStatusOutput(
        status=data if isinstance(data, dict) else {"value": data}
    ).model_dump()


async def server_ping(args: dict) -> dict:
    ServerPingInput(**args)
    try:
        data = api.request_json(
            "GET", "/ping", **_ctx(require_auth=False)
        )
    except api.WahaApiError as e:
        return ServerPingOutput(error=typed_error(e)).model_dump()
    pong = isinstance(data, dict) and str(
        data.get("message", "")
    ).lower() == "pong"
    return ServerPingOutput(pong=pong, raw=data).model_dump()


HANDLERS = {
    "waha.server.version": server_version,
    "waha.server.status": server_status,
    "waha.server.ping": server_ping,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="waha.server.version",
             description="WAHA build/engine version. READ-ONLY.",
             inputSchema=ServerVersionInput.model_json_schema()),
        Tool(name="waha.server.status",
             description="WAHA server status/uptime. READ-ONLY.",
             inputSchema=ServerStatusInput.model_json_schema()),
        Tool(name="waha.server.ping",
             description="UNAUTHENTICATED liveness probe (GET /ping) — "
             "'is the host up' independent of the API key. READ-ONLY.",
             inputSchema=ServerPingInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
