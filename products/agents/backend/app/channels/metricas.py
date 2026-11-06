"""Per-turn metrics recording (``agents.turn_metrics``, migration 066): cost, speed and size of ONE agent turn.

Money and tokens are SUMMED from the turn's own priced central-ledger events (``coletar_uso()``, the same
``UsageEvent`` objects the D25 sink receives) -- this module never prices anything. Speed comes from the clocks
``executar`` and the runtime read; size is UTF-8 payload bytes the app measured (not on-disk Postgres size).

``registrar_turno`` is the ONLY write path and is safe by construction: a failed metrics write is logged with its
traceback and swallowed (the turn already happened; observability must never fail it). It is called once, at the end.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = ["montar_registro", "registrar_turno", "tamanho_bytes"]


def tamanho_bytes(valor: Any) -> int:
    """UTF-8 bytes of a text, or of the JSON of a structure."""
    if valor is None:
        return 0
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    return len(texto.encode("utf-8"))


def _i(v: Any) -> int:
    return int(v or 0)


def montar_registro(
    *, org_id: UUID, agent: Any, versao_id: UUID | None, compiled_hash: str | None, thread_id: UUID | None,
    mensagem_entrada_id: UUID | None, mensagem_resposta_id: UUID | None, origem: str, gatilho: str | None,
    eventos: Iterable[Any], medida: dict[str, Any], turno_ms: int, intake_ms: int | None, inbound_bytes: int,
    reply_bytes: int, db_bytes: int, status: str, erro_classe: str | None = None, turno_status: str | None = None,
    handoff: bool = False, tools: Iterable[str] = (),
) -> dict[str, Any]:
    """The table row. ``eventos`` are the turn's ``UsageEvent``s; ``medida`` carries the runtime's clocks / prompt bytes
    (``llm_ms``, ``tool_ms``, ``tools_ms``, ``prompt_bytes``)."""
    eventos = list(eventos)
    leitura = sum(_i(e.cache_read_input_tokens) for e in eventos)
    escrita = sum(_i(e.cache_creation_input_tokens) for e in eventos)
    entrada = sum(_i(e.prompt_tokens) for e in eventos) + leitura + escrita
    return {
        "org_id": str(org_id), "agent_id": str(agent.id), "agent_key": agent.key,
        "version_id": str(versao_id) if versao_id else None, "compiled_hash": compiled_hash,
        "thread_id": str(thread_id) if thread_id else None,
        "inbound_message_id": str(mensagem_entrada_id) if mensagem_entrada_id else None,
        "reply_message_id": str(mensagem_resposta_id) if mensagem_resposta_id else None,
        "origem": origem, "gatilho": gatilho, "status": status, "erro_classe": erro_classe, "turno_status": turno_status,
        "handoff": bool(handoff), "tools": sorted(set(tools)),
        "llm_calls": len(eventos) or _i(medida.get("llm_calls")),
        "tokens_entrada": entrada, "tokens_saida": sum(_i(e.completion_tokens) for e in eventos),
        "tokens_cache_leitura": leitura, "tokens_cache_escrita": escrita,
        "custo_usd": round(sum(float(e.cost_estimate_usd or 0) for e in eventos), 6),
        "modelos": sorted({e.model for e in eventos if e.model}),
        "price_versions": sorted({e.price_version for e in eventos if e.price_version}),
        "turno_ms": _i(turno_ms), "llm_ms": _i(medida.get("llm_ms")), "tool_ms": _i(medida.get("tool_ms")),
        "tools_ms": dict(medida.get("tools_ms") or {}), "intake_ms": intake_ms,
        "inbound_bytes": _i(inbound_bytes), "reply_bytes": _i(reply_bytes), "prompt_bytes": _i(medida.get("prompt_bytes")),
        "db_bytes": _i(db_bytes), "media_bytes": None,
    }


def registrar_turno(store: Any | None, row: dict[str, Any]) -> None:
    """Write the turn's row; NEVER raises (logged with traceback). ``store=None`` = metrics not wired (a unit seam)."""
    if store is None:
        return
    try:
        store.registrar(row)
    except Exception:  # noqa: BLE001 -- observability must never fail a served turn; the failure is seen in the log
        logger.exception("agents.turn_metrics.registro_falhou agent_key=%s thread_id=%s", row.get("agent_key"), row.get("thread_id"))
