"""GitHub connector MCP server — stdio entry point.

Run:
    python mcp/github/server.py

Reads its non-secret routing config from env or `mcp/github/.env` (see
settings.py); credentials are owned by the operator's `gh` CLI keyring.
The server starts cleanly with no config — tools then return a typed,
never-faked `gh`-unavailable / unauthenticated signal (gated-capability
honesty) rather than a fabricated success.

Tool surface (all wrap the authenticated `gh` CLI, dotted naming):
- github.pr.list / view / diff / checks       — READ-ONLY
- github.pr.create / ready                     — WRITE, confirm-gated (412)
- github.repo.view                             — READ-ONLY
- github.diagnostics.connection_status         — READ-ONLY, never-faked

The stdio bootstrap (sys.path trick, in-tree seed pin, stderr logging,
Server + list_tools + call_tool + run loop) is shared across every
connector MCP in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from github.X import ...` AND `from _kit.X
# import ...` resolve cleanly. The PyPI `mcp` package shadows our `mcp/`
# dir as a namespace, so we import this connector package as top-level
# `github` and the shared kit as top-level `_kit` — same trick as
# `mcp/meta/server.py`. This bare insert MUST precede the first
# `_kit` / `github` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("github-mcp")

from github.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("github", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
