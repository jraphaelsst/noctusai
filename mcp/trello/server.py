"""Trello connector MCP server — stdio entry point.

Run:
    python mcp/trello/server.py

Primary job: a queryable map of Trello's product surface for designing
the shared lead-card-hub organ
(`project-history/roadmaps/lead-card-hub-2026-08.md`). Secondary job: a
correct, confirm-gated live client against the real Trello API.

Reads config from env or `mcp/trello/.env` (see settings.py). Starts
cleanly with NO config at all — the `trello.contract.*` and
`trello.diagnostics.connection_status` tools work immediately (zero IO,
reading only the vendored `contract/swagger.v3.json`); every credentialed
tool returns a typed, never-faked 424 rather than a fabricated success.

Tool surface (18 tools):
- trello.contract.list_endpoints        — READ, zero IO
- trello.contract.describe_operation    — READ, zero IO
- trello.contract.describe_model        — READ, zero IO
- trello.contract.card_surface          — READ, zero IO
- trello.contract.capability_map        — READ, zero IO
- trello.diagnostics.connection_status  — READ, zero API calls
- trello.diagnostics.probe              — READ, one live API call
- trello.boards.list                    — READ, one live API call
- trello.lists.list                     — READ, one live API call
- trello.cards.list                     — READ, one live API call
- trello.cards.get                      — READ, one live API call
- trello.checklists.get                 — READ, one live API call
- trello.labels.list                    — READ, one live API call
- trello.actions.list                   — READ, one live API call
- trello.cards.create                   — WRITE, confirm-gated (412)
- trello.cards.update                   — WRITE, confirm-gated (412)
- trello.cards.comment_add              — WRITE, confirm-gated (412)
- trello.checklists.create              — WRITE, confirm-gated (412)

The stdio bootstrap is shared across every connector MCP in
`_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from trello.X import ...` AND `from _kit.X
# import ...` resolve. The PyPI `mcp` package shadows our `mcp/` dir, so
# the connector is imported as top-level `trello`. This bare insert MUST
# precede the first `_kit` / `trello` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, prepare_sys_path, run_stdio_server

# Point `noctusai_lib` at THIS worktree's seed BEFORE the first import of
# it, in case any transitive import reaches for it. This connector does
# NOT depend on a seed adapter (deliberately — see settings.py's module
# docstring), but `prepare_sys_path` is still the correct universal first
# step every connector server takes.
prepare_sys_path(__file__)

# stdout is JSON-RPC; logs go to stderr.
logger = configure_stderr_logging("trello-mcp")

from trello.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("trello", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
