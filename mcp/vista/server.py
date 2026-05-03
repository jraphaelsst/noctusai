"""Vista CRM MCP server — stdio entry point.

Run:
    python mcp/vista/server.py

Reads VISTA_BASE_URL + VISTA_API_KEY from env or `mcp/vista/.env`. The
client deferred-config rule (see settings.py + client.py) means the
server starts cleanly even with no key — tool calls then return
typed `VistaConfigError`.

Tool surface (Phase 1 — see KB § INTEGRATIONS/vista.md § 7):
- vista.imoveis.{list, get, list_filters}    — live-probed
- vista.usuarios.list                         — live-probed
- vista.agencias.list                         — live-probed
- vista.clientes.list                         — permission-gated (returns typed_error on 401)
- vista.corretores.list                       — permission-gated (returns typed_error on 401)
- vista.diagnostics.{probe, list_known_endpoints, show_calibrated_fields}

Per-tenant calibration (vista.md § 6) runs lazily on first call to
imoveis/usuarios/agencias and caches per-process. Inspect via
`vista.diagnostics.show_calibrated_fields`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from vista.X import ...` resolves cleanly.
# (The PyPI `mcp` package shadows our `mcp/` dir as a namespace, so we
# import the Vista package as top-level `vista` instead — same trick as
# `mcp/noctusai/server.py`.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("vista-mcp")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from vista.tools import all_descriptors, all_handlers

server = Server("vista")
_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


@server.list_tools()
async def list_tools():
    return _DESCRIPTORS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        msg = {"error": f"unknown tool: {name}", "known_tools": sorted(_HANDLERS.keys())}
        return [TextContent(type="text", text=json.dumps(msg))]
    try:
        result = await handler(arguments or {})
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        logger.exception("vista tool %s raised: %s", name, e)
        err = {"error_class": type(e).__name__, "message": str(e)}
        return [TextContent(type="text", text=json.dumps(err))]


async def _main():
    logger.info(
        "vista-mcp starting — %d tools registered: %s",
        len(_DESCRIPTORS),
        sorted(_HANDLERS.keys()),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
