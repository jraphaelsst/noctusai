"""Cloudflare connector MCP server — stdio entry point.

Run:
    python mcp/cloudflare/server.py

Reads its config from env or `mcp/cloudflare/.env` (see settings.py).
The server starts cleanly with no config — tools then return a typed,
never-faked not-configured signal (gated-capability honesty) rather
than a fabricated success.

Tool surface (dotted naming, all via the Cloudflare API v4):
- cloudflare.zones.list / get                      — READ-ONLY
- cloudflare.zones.create                          — WRITE, confirm-gated (412)
- cloudflare.dns.list_records / get_record         — READ-ONLY
- cloudflare.dns.create_record / update_record     — WRITE, confirm-gated (412)
- cloudflare.dns.delete_record                     — WRITE, confirm-gated, STRONGEST (irreversible)
- cloudflare.tunnel.list / get / get_config        — READ-ONLY (account-scoped)
- cloudflare.tunnel.create / update_config         — WRITE, confirm-gated (412, account-scoped)
- cloudflare.tunnel.delete                         — WRITE, confirm-gated, STRONGEST (irreversible, account-scoped)
- cloudflare.diagnostics.connection_status         — READ-ONLY, never-faked

The stdio bootstrap (sys.path trick, in-tree seed pin, stderr logging,
Server + list_tools + call_tool + run loop) is shared across every
connector MCP in `_kit.bootstrap` — this module just composes it
(mirrors `mcp/hostinger/server.py` / `mcp/n8n/server.py`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from cloudflare.X import ...` AND `from
# _kit.X import ...` resolve cleanly. The PyPI `mcp` package shadows our
# `mcp/` dir as a namespace, so we import this connector package as
# top-level `cloudflare` and the shared kit as top-level `_kit` — same
# trick as `mcp/hostinger/server.py`. This bare insert MUST precede the
# first `_kit` / `cloudflare` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("cloudflare-mcp")

from cloudflare.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("cloudflare", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
