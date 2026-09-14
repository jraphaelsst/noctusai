"""academia MCP server — stdio entry point.

Run:
    python mcp/academia/server.py

Reads ACADEMIA_API_URL + ACADEMIA_API_TOKEN from env or `mcp/academia/.env`.
The not-configured rule (settings.py + client.py) means the server
starts cleanly even with no config — tool calls then return the typed
`{"ok": false, "error": {"code": "not_configured", ...}}` envelope
(CONTRACT §C build step 1).

Tool surface (CONTRACT §C) — 22 tools across 7 leaf modules:
- academia.kb.{buscar, ler, escrever, mover}
- academia.decisao.{registrar, listar, substituir}
- academia.pergunta.{adicionar, listar, responder}
- academia.historico.{append, timeline}
- academia.roadmap.{ler, atualizar}
- academia.tarefa.{criar, atualizar, listar, preparar_sessao}
- academia.conteudo.{salvar, listar, ler}
- academia.pesquisa.{capturar_fonte}

`academia.kb.index_sync`, `academia.kb.link_check` and
`academia.roadmap.render` are DEPRECATED and intentionally absent.

Not registered in noc's root `.mcp.json` — this connector is consumed
by the `agents` control plane's in-process SDK MCP server (CONTRACT
§E.5), not by Claude Code directly.

The stdio bootstrap (sys.path trick, stderr logging, the Server +
list_tools + call_tool + run loop) is shared across every connector MCP
in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from academia.X import ...` AND `from
# _kit.X import ...` resolve cleanly — same trick as
# `mcp/vista/server.py` / `mcp/noctusai/server.py`. This bare insert
# MUST happen before the first `_kit` / `academia` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("academia-mcp")

from academia.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("academia", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
