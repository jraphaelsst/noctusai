"""Vista CRM MCP server — stdio entry point.

Run:
    python mcp/vista/server.py

Reads VISTA_BASE_URL + VISTA_API_KEY from env or `mcp/vista/.env`. The
client deferred-config rule (see settings.py + client.py) means the
server starts cleanly even with no key — tool calls then return
typed `VistaConfigError`.

Tool surface (Phase 1 — see KB § INTEGRATIONS/vista.md § 7):
- vista.imoveis.{list, get, list_filters}    — live-probed
- vista.usuarios.list                         — live-probed
- vista.agencias.list                         — live-probed
- vista.clientes.list                         — permission-gated (returns typed_error on 401)
- vista.corretores.list                       — permission-gated (returns typed_error on 401)
- vista.diagnostics.{probe, list_known_endpoints, show_calibrated_fields}

Per-tenant calibration (vista.md § 6) runs lazily on first call to
imoveis/usuarios/agencias and caches per-process. Inspect via
`vista.diagnostics.show_calibrated_fields`.

The stdio bootstrap (sys.path trick, stderr logging, the Server +
list_tools + call_tool + run loop) is shared across every connector MCP
in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from vista.X import ...` AND `from _kit.X
# import ...` resolve cleanly. (The PyPI `mcp` package shadows our `mcp/`
# dir as a namespace, so we import the Vista package as top-level `vista`
# and the shared kit as top-level `_kit` — same trick as
# `mcp/noctusai/server.py`.) This bare insert MUST happen before the
# first `_kit` / `vista` import; `_kit.bootstrap.prepare_sys_path`
# repeats it idempotently for connectors that import the kit differently.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("vista-mcp")

from vista.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("vista", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
