"""ImovelWeb / OpenNavent connector MCP server — stdio entry point.

Run:
    python mcp/imovelweb/server.py

Covers ImovelWeb, Wimoveis and Casa Mineira, which share one OpenNavent
integration. **Not Grupo OLX** — that is a separate vendor with a separate
connector (`mcp/olx`), even though its Gestor de Leads also carries an
ImovelWeb bridge.

Reads config from env or `mcp/imovelweb/.env` (see settings.py). Starts
cleanly with no config at all: the zero-IO contract tools work
immediately, and the credentialed ones return a typed, never-faked 424
rather than a fabricated success.

Tool surface (19 tools):
- imovelweb.contract.describe             — READ, zero IO, no credentials
- imovelweb.contract.validate_payload     — READ, zero IO, no credentials
- imovelweb.contract.diff_observed        — READ, doc-vs-reality loop
- imovelweb.diagnostics.connection_status — READ, zero API calls
- imovelweb.diagnostics.probe             — READ
- imovelweb.diagnostics.list_known_endpoints — READ, no API calls
- imovelweb.diagnostics.fetch_swagger     — READ, public spec, no credentials
- imovelweb.callbacks.get_config          — READ
- imovelweb.callbacks.put_config          — WRITE, confirm-gated (412) ⚠️ integrator-wide
- imovelweb.callbacks.subscribe           — WRITE, confirm-gated (412)
- imovelweb.callbacks.unsubscribe         — WRITE, confirm-gated (412)
- imovelweb.leads.get_message             — READ
- imovelweb.leads.list_messages           — READ
- imovelweb.leads.get_smartlead           — READ
- imovelweb.leads.list_contact_actions    — READ
- imovelweb.agencies.list                 — READ
- imovelweb.sandbox.emit_event            — WRITE, confirm-gated (412), sandbox host only
- imovelweb.webhook.record_delivery       — WRITE, confirm-gated (412)
- imovelweb.webhook.simulate              — WRITE, confirm-gated (412)

The stdio bootstrap is shared across every connector MCP in
`_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from imovelweb.X import ...` AND `from _kit.X
# import ...` resolve. The PyPI `mcp` package shadows our `mcp/` dir, so
# the connector is imported as top-level `imovelweb`. This bare insert MUST
# precede the first `_kit` / `imovelweb` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, prepare_sys_path, run_stdio_server

# Point `noctusai_lib` at THIS worktree's seed BEFORE the first import of
# it. An editable install registers a meta-path finder that hard-pins
# `noctusai_lib` to whichever tree `pip install -e` last ran in, and
# meta-path finders are consulted before `sys.path` — so the bare insert
# above cannot override it on its own. Without this the server boots fine
# in the primary checkout and dies with `No module named
# 'noctusai_lib.integrations.imovelweb'` in any worktree, which is exactly
# where it gets developed.
prepare_sys_path(__file__)

# stdout is JSON-RPC; logs go to stderr.
logger = configure_stderr_logging("imovelweb-mcp")

from imovelweb.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("imovelweb", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
