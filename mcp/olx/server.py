"""OLX connector MCP server — stdio entry point.

Run:
    python mcp/olx/server.py

Covers every Grupo OLX portal (ZAP · VivaReal · OLX · ImovelWeb · Casa
Mineira) because they share one lead pipe.

Reads config from env or `mcp/olx/.env` (see settings.py). Starts
cleanly with no config at all — the zero-IO contract tools work
immediately, and the credentialed ones return a typed, never-faked
424 rather than a fabricated success.

Tool surface (8 tools):
- olx.webhook.describe_contract        — READ, zero IO, no credentials
- olx.webhook.validate_payload         — READ, zero IO, no credentials
- olx.contract.diff_observed           — READ, doc-vs-reality loop
- olx.webhook.record_delivery          — WRITE, confirm-gated (412)
- olx.webhook.simulate                 — WRITE, confirm-gated (412)
- olx.leads.push                       — WRITE, confirm-gated (412)
- olx.diagnostics.connection_status    — READ, zero API calls
- olx.diagnostics.probe                — READ
- olx.diagnostics.list_known_endpoints — READ, no API calls

The stdio bootstrap is shared across every connector MCP in
`_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from olx.X import ...` AND `from _kit.X
# import ...` resolve. The PyPI `mcp` package shadows our `mcp/` dir, so
# the connector is imported as top-level `olx`. This bare insert MUST
# precede the first `_kit` / `olx` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, prepare_sys_path, run_stdio_server

# Point `noctusai_lib` at THIS worktree's seed BEFORE the first import of
# it. An editable install registers a meta-path finder that hard-pins
# `noctusai_lib` to whichever tree `pip install -e` last ran in, and
# meta-path finders are consulted before `sys.path` — so the bare insert
# above cannot override it on its own. Without this the server boots fine
# in the primary checkout and dies with `No module named
# 'noctusai_lib.integrations.olx'` in any worktree, which is exactly
# where it gets developed.
prepare_sys_path(__file__)

# stdout is JSON-RPC; logs go to stderr.
logger = configure_stderr_logging("olx-mcp")

from olx.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("olx", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
