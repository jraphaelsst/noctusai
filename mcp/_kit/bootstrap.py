"""Connector-MCP shared stdio bootstrap.

Generalized from `mcp/vista/server.py`. Encapsulates the three things
every connector MCP server does identically:

1. `prepare_sys_path(server_file)` — put `mcp/` on `sys.path` so the
   connector package imports as a clean top-level name. The PyPI `mcp`
   package shadows our `mcp/` dir as a namespace, so connectors import
   their package as top-level `vista` / `meta` / `google` instead. The
   connector passes **its own** `Path(__file__)`; we insert
   `parents[1]` (the `mcp/` directory) exactly as vista did inline.
   MUST be called BEFORE the connector imports its own package.

2. `configure_stderr_logging(logger_name)` — route logs to stderr
   (stdio MCP owns stdout for JSON-RPC) with vista's exact format, and
   return the named logger.

3. `run_stdio_server(server_name, descriptors, handlers, logger)` — the
   `Server(...)` + `@list_tools` + `@call_tool` (server-level error
   envelope + `logger.exception`) + `stdio_server()` run loop,
   byte-for-behavior identical to vista's original `call_tool` / `_main`.

NOTE on the error envelope. Vista's *server-level* catch-all emitted a
TWO-key payload `{"error_class", "message"}` (NO `status`). The THREE-key
`_kit.errors.typed_error` (`+status`) generalizes vista's *per-tool*
`_typed_error`, whose real use site is INSIDE tool handlers (nested as
`{"error": typed_error(e)}` in the tool's own result) — a path that never
reaches this catch-all. To honour the ZERO-behavior-change contract, this
loop preserves the exact 2-key server-level shape; `typed_error` stays the
shared helper for the tool-handler internals where the 3-key shape lives.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


def prepare_sys_path(server_file: str | Path) -> None:
    """Insert the `mcp/` dir (parents[1] of the connector's server.py)
    at the front of sys.path. Idempotent-ish: mirrors vista's original
    `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`."""
    sys.path.insert(0, str(Path(server_file).resolve().parents[1]))


def configure_stderr_logging(logger_name: str) -> logging.Logger:
    """Route logs to stderr with vista's exact format; return the logger."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    return logging.getLogger(logger_name)


async def run_stdio_server(
    server_name: str,
    descriptors: list,
    handlers: dict,
    logger: logging.Logger,
) -> None:
    """Run the stdio MCP server loop for a connector.

    `server_name`  — MCP server identity (e.g. "vista").
    `descriptors`  — pre-built list[Tool] (connector calls all_descriptors()).
    `handlers`     — pre-built {name: async-handler} (all_handlers()).
    `logger`       — the connector's logger (from configure_stderr_logging).

    The unknown-tool branch, the typed-error envelope, the
    `json.dumps(..., indent=2, default=str)` success shape, and the
    `logger.exception` call are all preserved exactly from vista's
    original `server.py` so refactoring vista onto this is zero-behavior.
    """
    # Imported here (not at module top) so importing `_kit.bootstrap`
    # does NOT require the PyPI `mcp` package to be installed — keeps
    # the kit unit-testable in a bare environment.
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent

    server = Server(server_name)

    @server.list_tools()
    async def list_tools():
        return descriptors

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        handler = handlers.get(name)
        if handler is None:
            msg = {
                "error": f"unknown tool: {name}",
                "known_tools": sorted(handlers.keys()),
            }
            return [TextContent(type="text", text=json.dumps(msg))]
        try:
            result = await handler(arguments or {})
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except Exception as e:  # noqa: BLE001 — re-rendered as 2-key envelope below
            logger.exception("%s tool %s raised: %s", server_name, name, e)
            # Vista's exact server-level shape — TWO keys, NO status.
            # (The 3-key typed_error lives in tool-handler internals.)
            err = {"error_class": type(e).__name__, "message": str(e)}
            return [TextContent(type="text", text=json.dumps(err))]

    logger.info(
        "%s-mcp starting — %d tools registered: %s",
        server_name,
        len(descriptors),
        sorted(handlers.keys()),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


__all__ = ["prepare_sys_path", "configure_stderr_logging", "run_stdio_server"]
