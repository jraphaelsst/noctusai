"""Live progress of an eval run (owner 2026-11-17: "I need to see progress ... live-streaming results and numbers updating").

Pure functions over what the stores already hold, so the screen's numbers are the server's, not the client's guesses:
cases done / total, passed / failed / errored, the running score (errored cases are not measurements: out of the
denominator), the cost so far against the cap, elapsed time and an ETA from the pace so far.

The behaviour suite writes each case as it finishes (``eval_results``), so its progress is exact and the per-case rows
appear live. The mechanism suite stores its executions only when the whole run ends, so its progress is ``indeterminado``:
status, elapsed time, cost cap and (once finished) the final counters -- never an invented percentage.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

__all__ = ["ATIVOS", "progresso_comportamento", "progresso_mecanismo"]

ATIVOS = ("pendente", "executando")
_MEDIDOS = ("aprovado", "reprovado")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


def _tempos(inicio: datetime | None, fim: datetime | None, agora: datetime) -> float | None:
    ini = _aware(inicio)
    if ini is None:
        return None
    return round(max(0.0, ((_aware(fim) or agora) - ini).total_seconds()), 1)


def progresso_comportamento(run: Any, resultados: Sequence[Any], *, agora: datetime | None = None) -> dict[str, Any]:
    """``run`` = ``EvalRunRecord``; ``resultados`` = ``EvalResultRecord`` rows of the run (``pendente`` ones included)."""
    agora = agora or _agora()
    por = {s: 0 for s in ("pendente", "aprovado", "reprovado", "erro", "pulado")}
    notas: list[float] = []
    custo = 0.0
    for r in resultados:
        por[r.status] = por.get(r.status, 0) + 1
        if r.status in _MEDIDOS and r.score is not None:
            notas.append(float(r.score))
        custo += float(r.custo_usd or 0.0)
    total = int(run.total or len(resultados))
    concluidos = por["aprovado"] + por["reprovado"] + por["erro"] + por["pulado"]
    decorrido = _tempos(run.started_at, run.finished_at, agora)
    ativo = run.status in ATIVOS
    eta = None
    if ativo and decorrido is not None and 0 < concluidos < total:
        eta = round(decorrido / concluidos * (total - concluidos), 1)
    return {
        "run_id": run.id, "suite": "comportamento", "status": run.status, "ativo": ativo, "indeterminado": False,
        "total": total, "concluidos": concluidos, "aprovados": por["aprovado"], "reprovados": por["reprovado"],
        "erros": por["erro"], "pulados": por["pulado"],
        # errored cases are no measurement: nothing measured => no score (never a 0%)
        "score_parcial": round(sum(notas) / len(notas), 3) if notas else None,
        "custo_usd": round(max(custo, float(run.custo_usd or 0.0)), 4), "limite_usd": run.limite_usd,
        "started_at": run.started_at, "finished_at": run.finished_at, "decorrido_s": decorrido, "eta_s": eta,
        "erro": run.erro, "erro_codigo": getattr(run, "erro_codigo", None),
    }


def progresso_mecanismo(run: dict[str, Any], run_id: UUID, *, agora: datetime | None = None) -> dict[str, Any]:
    """``run`` = the mechanism run row. Its executions are stored only when the run ends: while it executes the numbers are
    unknown (``indeterminado``), never faked."""
    agora = agora or _agora()
    ativo = run["status"] == "executando"
    fim = run.get("finished_at") or (None if ativo else run.get("updated_at"))
    total = int(run.get("total_casos") or 0)
    aprovados = int(run.get("casos_aprovados") or 0)
    final = not ativo and run["status"] == "concluida"
    custo = run.get("custo_usd")
    return {
        "run_id": run_id, "suite": "mecanismo", "status": run["status"], "ativo": ativo, "indeterminado": ativo,
        "total": total, "concluidos": total if final else None, "aprovados": aprovados if final else None,
        "reprovados": total - aprovados if final else None, "erros": None, "pulados": None,
        "score_parcial": (aprovados / total) if final and total else None,
        "custo_usd": float(custo) if custo is not None else None, "limite_usd": run.get("limite_usd"),
        "started_at": run.get("started_at") or run.get("created_at"), "finished_at": fim,
        "decorrido_s": _tempos(run.get("started_at") or run.get("created_at"), fim, agora), "eta_s": None,
        "erro": run.get("erro"), "erro_codigo": "mecanismo_falhou" if run["status"] == "falhou" else None,
    }
