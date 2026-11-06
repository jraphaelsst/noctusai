"""Pure aggregation + shaping of ``agents.turn_metrics`` rows (platform-admin metrics page; no IO).

Percentiles use linear interpolation between closest ranks (the numpy ``linear`` default), over the rows of the
window. Cache share is ``cache_read / tokens_entrada`` (tokens_entrada already includes cache read + write).
Cost is the SUM of stored per-turn costs (themselves sums of priced ledger events) -- nothing is re-priced.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

__all__ = ["percentil", "resumir", "serie_diaria", "turno_publico", "por_chave"]


def percentil(valores: Iterable[float], p: float) -> float | None:
    """The ``p`` percentile (0..100), linear interpolation; ``None`` for no values."""
    v = sorted(valores)
    if not v:
        return None
    if len(v) == 1:
        return float(v[0])
    pos = (len(v) - 1) * p / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return float(v[lo] + (v[hi] - v[lo]) * (pos - lo))


def _r(x: float | None, n: int = 1) -> float | None:
    return None if x is None else round(x, n)


def _share(parte: int, todo: int) -> float:
    return round(parte / todo, 4) if todo else 0.0


def resumir(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    custo = sum(float(r["custo_usd"] or 0) for r in rows)
    entrada = sum(r["tokens_entrada"] for r in rows)
    leitura = sum(r["tokens_cache_leitura"] for r in rows)
    return {
        "turnos": n,
        "turnos_erro": sum(1 for r in rows if r["status"] == "erro"),
        "handoffs": sum(1 for r in rows if r.get("handoff")),
        "llm_calls": sum(r["llm_calls"] for r in rows),
        "custo_usd": round(custo, 6),
        "custo_por_turno_usd": round(custo / n, 6) if n else 0.0,
        "tokens_entrada": entrada,
        "tokens_saida": sum(r["tokens_saida"] for r in rows),
        "tokens_cache_leitura": leitura,
        "tokens_cache_escrita": sum(r["tokens_cache_escrita"] for r in rows),
        "cache_leitura_share": _share(leitura, entrada),
        "turno_ms_p50": _r(percentil((r["turno_ms"] for r in rows), 50)),
        "turno_ms_p95": _r(percentil((r["turno_ms"] for r in rows), 95)),
        "llm_ms_p50": _r(percentil((r["llm_ms"] for r in rows), 50)),
        "llm_ms_p95": _r(percentil((r["llm_ms"] for r in rows), 95)),
        "tool_ms_p50": _r(percentil((r["tool_ms"] for r in rows), 50)),
        "tool_ms_p95": _r(percentil((r["tool_ms"] for r in rows), 95)),
        "inbound_bytes": sum(r["inbound_bytes"] for r in rows),
        "reply_bytes": sum(r["reply_bytes"] for r in rows),
        "prompt_bytes": sum(r["prompt_bytes"] for r in rows),
        "db_bytes": sum(r["db_bytes"] for r in rows),
        "armazenamento_bytes": sum(r["db_bytes"] for r in rows),
    }


def por_chave(rows: list[dict[str, Any]], chave: Callable[[dict[str, Any]], Any], nome: str) -> list[dict[str, Any]]:
    """``resumir`` per group, groups ordered by cost desc. ``nome`` is the key the group value is returned under."""
    grupos: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grupos[chave(r)].append(r)
    out = [{nome: k, **resumir(v)} for k, v in grupos.items()]
    return sorted(out, key=lambda g: g["custo_usd"], reverse=True)


def serie_diaria(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One point per UTC day with turns, cost and speed, oldest first."""
    dias = por_chave(rows, lambda r: r["created_at"].date().isoformat(), "dia")
    return sorted(dias, key=lambda d: d["dia"])


def turno_publico(r: dict[str, Any]) -> dict[str, Any]:
    entrada = r["tokens_entrada"]
    return {
        "id": str(r["id"]), "criado_em": r["created_at"].isoformat(), "org_id": str(r["org_id"]),
        "agent_key": r["agent_key"], "version_id": r.get("version_id"), "compiled_hash": r.get("compiled_hash"),
        "thread_id": r.get("thread_id"), "mensagem_entrada_id": r.get("inbound_message_id"),
        "mensagem_resposta_id": r.get("reply_message_id"), "origem": r["origem"], "gatilho": r.get("gatilho"),
        "status": r["status"], "erro_classe": r.get("erro_classe"), "turno_status": r.get("turno_status"),
        "handoff": bool(r.get("handoff")), "ferramentas": list(r.get("tools") or []),
        "llm": {
            "chamadas": r["llm_calls"], "tokens_entrada": entrada, "tokens_saida": r["tokens_saida"],
            "tokens_cache_leitura": r["tokens_cache_leitura"], "tokens_cache_escrita": r["tokens_cache_escrita"],
            "cache_leitura_share": _share(r["tokens_cache_leitura"], entrada), "custo_usd": float(r["custo_usd"] or 0),
            "modelos": list(r.get("modelos") or []), "price_versions": list(r.get("price_versions") or []),
        },
        "velocidade": {
            "turno_ms": r["turno_ms"], "llm_ms": r["llm_ms"], "tool_ms": r["tool_ms"],
            "ferramentas_ms": dict(r.get("tools_ms") or {}), "intake_ms": r.get("intake_ms"),
        },
        "tamanho": {
            "inbound_bytes": r["inbound_bytes"], "reply_bytes": r["reply_bytes"], "prompt_bytes": r["prompt_bytes"],
            "db_bytes": r["db_bytes"], "media_bytes": r.get("media_bytes"),
        },
    }
