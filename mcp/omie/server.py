"""Omie ERP MCP server — stdio entry point.

Run:
    python mcp/omie/server.py

Reads its Omie environments from the process env or `mcp/omie/.env`
(see `settings.py`). The server starts cleanly with no credentials
configured — tool calls then return a typed `OmieConfigError`, and
`omie.diagnostics.connection_status` explains what to set.

Tool surface:
  omie.environments.{list, describe, check}        — which company am I on?
  omie.catalog.{search, describe_method,
                list_endpoints, endpoint_methods,
                status}                            — offline API discovery
  omie.call.{invoke, paginate}                     — ALL 461 Omie methods
  omie.<resource>.{list, get, upsert, delete}      — curated high-traffic CRUD
  omie.diagnostics.{connection_status,
                    rate_limit_status}             — health + throttle state

The stdio bootstrap (sys.path trick, stderr logging, the Server +
list_tools + call_tool + run loop) is shared across every connector MCP
in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from omie.X import ...` AND `from _kit.X import
# ...` resolve cleanly. (The PyPI `mcp` package shadows our `mcp/` dir as a
# namespace, so we import the Omie package as top-level `omie` and the shared
# kit as top-level `_kit`.) This bare insert MUST happen before the first
# `_kit` / `omie` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("omie-mcp")

from omie.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("omie", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
