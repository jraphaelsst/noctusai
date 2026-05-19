"""WAHA connector MCP server — stdio entry point.

Run:
    python mcp/waha/server.py

Reads its config from env or `mcp/waha/.env` (see settings.py). Boots
cleanly with no config — tools then return a typed, never-faked
not-configured signal (gated-capability honesty).

Tool surface (dotted naming, all via the WAHA HTTP API):
- waha.session.list / get / me                 — READ-ONLY
- waha.session.start / stop / restart / logout — WRITE, confirm-gated (412)
- waha.message.send_text                       — WRITE, confirm-gated, OUTWARD
- waha.message.list / waha.chat.list           — READ-ONLY
- waha.server.version / status / ping          — READ-ONLY (ping = unauth)
- waha.diagnostics.connection_status           — READ-ONLY, never-faked

The stdio bootstrap is shared in `_kit.bootstrap` — this module just
composes it (mirrors `mcp/n8n/server.py`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from waha.X import ...` AND `from _kit.X
# import ...` resolve cleanly (PyPI-`mcp`-shadow trick — same as
# `mcp/n8n/server.py`). MUST precede the first `_kit` / `waha` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

logger = configure_stderr_logging("waha-mcp")

from waha.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("waha", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
