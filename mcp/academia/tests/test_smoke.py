"""Smoke tests for the academia connector MCP.

No network: registry coherence, 3-segment dotted naming, deprecated-
tool absence (CONTRACT §C), gated-capability honesty (settings never
crash on missing config), and a real server-process boot check.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_EXPECTED_TOOLS = {
    "academia.kb.buscar",
    "academia.kb.ler",
    "academia.kb.escrever",
    "academia.kb.mover",
    "academia.decisao.registrar",
    "academia.decisao.listar",
    "academia.decisao.substituir",
    "academia.pergunta.adicionar",
    "academia.pergunta.listar",
    "academia.pergunta.responder",
    "academia.historico.append",
    "academia.historico.timeline",
    "academia.roadmap.ler",
    "academia.roadmap.atualizar",
    "academia.tarefa.criar",
    "academia.tarefa.atualizar",
    "academia.tarefa.listar",
    "academia.tarefa.preparar_sessao",
    "academia.conteudo.salvar",
    "academia.conteudo.listar",
    "academia.conteudo.ler",
    "academia.pesquisa.capturar_fonte",
}

#: CONTRACT §C — deprecated, deliberately removed. A future re-addition
#: of any of these is a contract violation, not an oversight.
_DEPRECATED_TOOLS = {
    "academia.kb.index_sync",
    "academia.kb.link_check",
    "academia.roadmap.render",
}


# ─── composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from academia import client, settings, types  # noqa: F401
    from academia.tools import conteudo, decisao, historico, kb, pergunta, pesquisa, projeto  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401


def test_registered_tool_name_set_is_pinned():
    from academia.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_deprecated_tools_are_absent():
    """CONTRACT §C: `kb.index_sync`, `kb.link_check`, `roadmap.render`
    are deprecated + removed. No leaf module registers them."""
    from academia.tools import all_handlers

    registered = set(all_handlers().keys())
    overlap = registered & _DEPRECATED_TOOLS
    assert not overlap, f"deprecated tool(s) still registered: {overlap}"


def test_descriptors_match_handlers():
    from academia.tools import all_descriptors, all_handlers

    descriptors = all_descriptors()
    handlers = all_handlers()
    descriptor_names = {d.name for d in descriptors}
    handler_names = set(handlers.keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_dotted_naming_convention():
    from academia.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "academia", f"tool {name!r} not under academia.* umbrella"


def test_every_descriptor_states_leitura_or_escrita():
    """Build step 3: PT-BR descriptions, each stating LEITURA or ESCRITA."""
    from academia.tools import all_descriptors

    for d in all_descriptors():
        assert "LEITURA" in d.description or "ESCRITA" in d.description, (
            f"{d.name!r} description does not state LEITURA/ESCRITA: {d.description!r}"
        )


# ─── settings — lenient, never crashes, no default URL ──────────────────


def test_settings_lenient_no_config():
    from academia.settings import AcademiaSettings

    s = AcademiaSettings()
    assert s.configured is False
    assert s.api_url is None
    assert s.api_token is None


# ─── server boot ──────────────────────────────────────────────────────────


def test_server_boots_and_registers_every_tool():
    """Runs the real stdio entrypoint as a subprocess with stdin closed
    (so it blocks on `stdio_server()` without ever getting a JSON-RPC
    frame) and asserts the startup log line lists every registered
    tool. No network, no MCP client — a pure process-boot smoke test."""
    proc = subprocess.run(
        [sys.executable, "mcp/academia/server.py"],
        cwd=str(_REPO_ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # stdio_server() exits (rc 0) once stdin closes with EOF — the run
    # loop ends cleanly rather than hanging.
    assert proc.returncode == 0, proc.stderr
    assert "academia-mcp starting" in proc.stderr
    assert "22 tools registered" in proc.stderr
    for name in _EXPECTED_TOOLS:
        assert name in proc.stderr, f"{name!r} missing from startup log"
    for name in _DEPRECATED_TOOLS:
        assert name not in proc.stderr, f"deprecated tool {name!r} logged at startup"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
