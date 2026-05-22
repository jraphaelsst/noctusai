"""Supabase Management API connector MCP server — stdio entry point.

Run:
    python mcp/supabase/server.py

Reads its config from env or `mcp/supabase/.env` (see settings.py).
The server starts cleanly with no config — tools then return a typed,
never-faked not-configured signal (gated-capability honesty) rather
than a fabricated success.

Tool surface (dotted naming, all via the Supabase Management API):
- supabase.project.list / get                      — READ-ONLY
- supabase.db.query                                — read free / write confirm-gated (412)
- supabase.db.list_tables / list_schemas           — READ-ONLY (via information_schema)
- supabase.migration.list                          — READ-ONLY
- supabase.migration.apply                         — WRITE, confirm-gated (412)
- supabase.diagnostics.connection_status           — READ-ONLY, never-faked

The stdio bootstrap (sys.path trick, in-tree seed pin, stderr logging,
Server + list_tools + call_tool + run loop) is shared across every
connector MCP in `_kit.bootstrap` — this module just composes it
(mirrors `mcp/cloudflare/server.py` / `mcp/n8n/server.py`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from supabase.X import ...` AND `from
# _kit.X import ...` resolve cleanly. The PyPI `mcp` package shadows our
# `mcp/` dir as a namespace, so we import this connector package as
# top-level `supabase` and the shared kit as top-level `_kit` — same
# trick as `mcp/cloudflare/server.py`. This bare insert MUST precede the
# first `_kit` / `supabase` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("supabase-mcp")

from supabase.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("supabase", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
