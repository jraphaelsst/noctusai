"""One eval run / eval loop per USER at a time (owner 2026-11-12).

A user (the run's ``started_by``: the human's user id, or the token row id for a ``studio:evals-run`` token) with a run in
flight (behaviour ``pendente``/``executando``, mechanism ``executando`` — any agent, either suite, single run or loop round) is
refused when starting ANY other run -> 409 ``execucao_em_andamento``. A user with an ACTIVE loop may start only that loop's next
round: a second loop, a single run, or a round of another loop -> 409 ``loop_ativo_do_usuario``. Another user is never affected.

The API check here names what is running (pt-BR + the run's id/agent/suite/loop for the UI); the DB trigger of migration 087
(per-user advisory lock + the same predicate) is the race-safe backstop, so two simultaneous starts can never both book. Every
refusal is recorded as an append-only event (``agents.eval_recusas_eventos``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger("agents.studio.eval_um_por_usuario")

__all__ = ["RunEmAndamento", "checar_um_por_usuario", "CODIGO_EM_ANDAMENTO", "CODIGO_LOOP_ATIVO"]

CODIGO_EM_ANDAMENTO = "execucao_em_andamento"
CODIGO_LOOP_ATIVO = "loop_ativo_do_usuario"
_ROTULO_SUITE = {"comportamento": "comportamento", "mecanismo": "mecanismo"}


@dataclass(frozen=True)
class RunEmAndamento:
    run_id: UUID
    org_id: UUID
    agent_id: UUID
    suite: str  # comportamento | mecanismo
    status: str


def checar_um_por_usuario(
    *, started_by: UUID, org_id: UUID, agent_id: UUID, suite: str, loop_id: UUID | None, abrindo_loop: bool = False,
    fase: str = "tudo", runs: Any, mecanismo: Any, loops: Any, chave_do_agente: Callable[[UUID], str | None],
) -> None:
    """Raise the 409 when ``started_by`` may not start this run (or open this loop); return ``None`` when it may.

    ``loop_id`` = the loop this run is a round of (``None`` for a single run); ``abrindo_loop`` = opening a loop (no run yet).
    Order: (1) a run in flight; (2) an active loop that is not the one being continued. ``fase`` = ``em_andamento`` | ``loop`` |
    ``tudo``: a loop round checks (1) BEFORE the loop admission (which would otherwise say only "a round is open") and (2) AFTER it
    (so an unknown loop is a 404 and a loop of the other suite a 422 first)."""
    em_voo = [*runs.em_andamento_do_usuario(started_by), *mecanismo.em_andamento_do_usuario(started_by)] if fase != "loop" else []
    if em_voo:
        r = em_voo[0]
        dentro = loops.rodada_do_run(r.org_id, r.run_id, r.suite)
        chave = chave_do_agente(r.agent_id) or "outro agente"
        onde = f"{chave} · {_ROTULO_SUITE[r.suite]}"
        if dentro is not None:
            onde += f", rodada {dentro[1].seq} do loop"
        detalhe = {
            "run_id": str(r.run_id), "agent_key": chave, "suite": r.suite, "status": r.status,
            "loop_id": None if dentro is None else str(dentro[0].id), "rodada": None if dentro is None else dentro[1].seq}
        _recusar(
            loops, CODIGO_EM_ANDAMENTO, started_by=started_by, org_id=org_id, agent_id=agent_id, suite=suite, loop_id=loop_id,
            mensagem=f"Você já tem uma avaliação em andamento ({onde}). Aguarde terminar ou cancele-a antes de iniciar outra.",
            em_andamento=detalhe, em_andamento_run=(r.run_id, r.suite), em_andamento_loop=None if dentro is None else dentro[0].id)
    ativos = [l for l in loops.loops_ativos_do_usuario(started_by) if l.id != loop_id] if fase != "em_andamento" else []
    if ativos:
        l = ativos[0]
        onde = f"{l.agente_chave} · {_ROTULO_SUITE[l.suite]}"
        if abrindo_loop:
            acao = "Finalize-o ou pare-o (\"Parar loop\") antes de abrir outro."
        elif loop_id is not None:
            acao = "Continue as rodadas dele ou pare-o (\"Parar loop\") antes de iniciar rodadas de outro loop."
        else:
            acao = "Continue as rodadas dele ou pare-o (\"Parar loop\") antes de iniciar uma avaliação avulsa."
        _recusar(
            loops, CODIGO_LOOP_ATIVO, started_by=started_by, org_id=org_id, agent_id=agent_id, suite=suite, loop_id=loop_id,
            mensagem=f"Você já tem um loop de avaliação ativo ({onde}). {acao}",
            em_andamento={"loop_id": str(l.id), "agent_key": l.agente_chave, "suite": l.suite}, em_andamento_run=None,
            em_andamento_loop=l.id)


def _recusar(
    loops: Any, codigo: str, *, started_by: UUID, org_id: UUID, agent_id: UUID, suite: str, loop_id: UUID | None, mensagem: str,
    em_andamento: dict[str, Any], em_andamento_run: tuple[UUID, str] | None, em_andamento_loop: UUID | None,
) -> None:
    logger.warning(
        "agents.studio.eval_um_por_usuario.recusa code=%s user=%s agent=%s suite=%s loop=%s blocking=%s",
        codigo, started_by, agent_id, suite, loop_id, em_andamento)
    try:
        loops.registrar_recusa(
            org_id=org_id, started_by=started_by, codigo=codigo, agent_id=agent_id, suite=suite, loop_id=loop_id,
            em_andamento_run=em_andamento_run, em_andamento_loop=em_andamento_loop)
    except Exception:  # noqa: BLE001 -- the refusal itself stands; a failed event write is logged, never swallowed silently
        logger.exception("agents.studio.eval_um_por_usuario.recusa_nao_registrada code=%s user=%s", codigo, started_by)
    raise HTTPException(409, detail={"detail": mensagem, "code": codigo, "em_andamento": em_andamento})
