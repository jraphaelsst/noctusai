"""n8n connector MCP server — stdio entry point.

Run:
    python mcp/n8n/server.py

Reads its config from env or `mcp/n8n/.env` (see settings.py). The
server starts cleanly with no config — tools then return a typed,
never-faked not-configured signal (gated-capability honesty) rather
than a fabricated success.

Tool surface (dotted naming, 16 tools total — see `README.md` for the
full endpoint table):
- n8n.workflow.list / get                      — READ-ONLY
- n8n.workflow.activate / deactivate           — WRITE, confirm-gated (412)
- n8n.workflow.update / create / delete        — WRITE, confirm-gated (412)
- n8n.workflow.set_tags                        — WRITE, confirm-gated (412)
- n8n.execution.list / get                     — READ-ONLY (failure diag)
- n8n.execution.delete                         — WRITE, confirm-gated (412)
- n8n.tag.list                                 — READ-ONLY
- n8n.credential.schema                        — READ-ONLY (type discovery)
- n8n.credential.create / delete               — WRITE, confirm-gated (412)
- n8n.diagnostics.connection_status            — READ-ONLY, never-faked

The stdio bootstrap (sys.path trick, in-tree seed pin, stderr logging,
Server + list_tools + call_tool + run loop) is shared across every
connector MCP in `_kit.bootstrap` — this module just composes it
(mirrors `mcp/github/server.py`).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from n8n.X import ...` AND `from _kit.X
# import ...` resolve cleanly. The PyPI `mcp` package shadows our `mcp/`
# dir as a namespace, so we import this connector package as top-level
# `n8n` and the shared kit as top-level `_kit` — same trick as
# `mcp/github/server.py`. This bare insert MUST precede the first
# `_kit` / `n8n` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("n8n-mcp")

from n8n.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("n8n", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
