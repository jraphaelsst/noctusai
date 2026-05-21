"""Hostinger connector MCP server — stdio entry point.

Run:
    python mcp/hostinger/server.py

Reads its config from env or `mcp/hostinger/.env` (see settings.py).
The server starts cleanly with no config — tools then return a typed,
never-faked not-configured signal (gated-capability honesty) rather
than a fabricated success.

Tool surface (dotted naming, all via the Hostinger Developers API):
- hostinger.vps.list / get / metrics / actions  — READ-ONLY
- hostinger.vps.restart / start                 — WRITE/POWER, confirm-gated (412)
- hostinger.vps.stop                            — WRITE/POWER, confirm-gated, STRONGEST (takes the server down)
- hostinger.diagnostics.connection_status       — READ-ONLY, never-faked

The stdio bootstrap (sys.path trick, in-tree seed pin, stderr logging,
Server + list_tools + call_tool + run loop) is shared across every
connector MCP in `_kit.bootstrap` — this module just composes it
(mirrors `mcp/n8n/server.py` / `mcp/waha/server.py`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from hostinger.X import ...` AND `from
# _kit.X import ...` resolve cleanly. The PyPI `mcp` package shadows our
# `mcp/` dir as a namespace, so we import this connector package as
# top-level `hostinger` and the shared kit as top-level `_kit` — same
# trick as `mcp/n8n/server.py`. This bare insert MUST precede the first
# `_kit` / `hostinger` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("hostinger-mcp")

from hostinger.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("hostinger", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
