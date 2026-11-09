"""Run the mechanism suite of one agent version and record it (Julia v2 A-EVAL).

The orchestration the (platform-admin) trigger calls: load the active ``mecanismo`` cases, drive them through
the injected :class:`EvalTurnDriver`, persist the per-execution outcomes, and stamp the run. The run is stamped
with the driver's ``tipo``; only ``live`` runs can open the publish gate (``eval_mecanismo.decidir_portao``).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.studio.eval_driver import EvalTurnDriver
from app.studio.eval_mecanismo import SuiteResultado, executar_suite

logger = logging.getLogger(__name__)

__all__ = ["ORFA_ERRO", "varrer_runs_orfas", "SuiteVazia", "TodosConsolidados", "DriverSemTipo", "rodar_suite_mecanismo", "iniciar_suite_mecanismo", "concluir_suite_mecanismo"]

_TIPOS = ("live", "fake")
#: The fixed ``erro`` of a run whose runner died with the process.
ORFA_ERRO = "interrompida"


def varrer_runs_orfas(store: Any, *, started_before: Any = None) -> int:
    """Startup: every mechanism run still ``executando`` that began before this process booted lost its background
    task with the previous process -- mark it ``falhou`` / ``interrompida`` so the one-run-per-version slot is free
    again. Exact for the single-replica deploy (same approximation as the judge runs'
    ``sweep_orphaned_runs``; NOC-REMEDIATE[eval-run-instance-id] covers a multi-replica deploy)."""
    from app.stores._util import utcnow

    n = store.fail_orphaned_runs(started_before=started_before or utcnow(), erro=ORFA_ERRO)
    if n:
        logger.warning("agents.eval.mecanismo_orphaned_runs_failed count=%s", n)
    return n


class SuiteVazia(RuntimeError):
    """The agent has no active mecanismo case: there is nothing to run (and nothing to approve)."""


class TodosConsolidados(RuntimeError):
    """Every active mechanism case is consolidated and unaffected: a default run would execute nothing (use ``rodar_tudo``)."""


class DriverSemTipo(RuntimeError):
    """The driver does not declare ``tipo`` in ('live','fake'): refuse rather than guess (fail closed)."""


def iniciar_suite_mecanismo(
    store: Any,
    driver: EvalTurnDriver,
    *,
    org_id: UUID,
    agent_id: UUID,
    version_id: UUID,
    compiled_hash: str,
    started_by: UUID,
    limite_usd: float | None,
    consolidacao: Any = None,
    partes: Any = None,
    rodar_tudo: bool = False,
) -> tuple[UUID, list]:
    """Validate the driver, load the active cases and book the run (``executando``). Returns ``(run_id, casos)``.
    The first half of a run: the HTTP trigger does this synchronously (so a refusal is a 409 at once) and hands the
    execution to :func:`concluir_suite_mecanismo` in the background.

    ``consolidacao`` (eval consolidation store): a default run (not ``rodar_tudo``) drops the cases that are consolidated and
    unaffected and records them as skipped against the run; the publish gate then counts those still-consolidated cases as covered."""
    tipo = getattr(driver, "tipo", None)
    if tipo not in _TIPOS:
        raise DriverSemTipo("driver.tipo must be 'live' or 'fake'")
    casos = store.list_active_cases(org_id, agent_id)
    if not casos:
        raise SuiteVazia("no active mecanismo case")
    sel = None
    if consolidacao is not None:
        from app.studio.consolidacao_service import selecionar

        sel = selecionar(
            consolidacao, org_id=org_id, agent_id=agent_id, suite="mecanismo", ativos=[c.id for c in casos],
            partes=partes, hash_atual=compiled_hash, rodar_tudo=rodar_tudo)
        if not sel.rodar:
            raise TodosConsolidados("every active mecanismo case is consolidated and unaffected")
        if sel.pulados:
            quer = set(sel.rodar)
            casos = [c for c in casos if c.id in quer]
    run_id = store.start_run(
        org_id, agent_id, version_id, compiled_hash=compiled_hash, driver=tipo,
        limite_usd=limite_usd, started_by=started_by, total_casos=len(casos),
    )
    if sel is not None:
        from app.studio.consolidacao_service import confirmar_selecao

        try:
            confirmar_selecao(
                consolidacao, sel, org_id=org_id, agent_id=agent_id, suite="mecanismo", run_id=run_id,
                run_tipo="mecanismo", partes=partes, hash_atual=compiled_hash)
        except Exception:
            store.fail_run(org_id, run_id, erro="consolidacao_indisponivel")
            raise
    return run_id, casos


async def concluir_suite_mecanismo(
    store: Any, driver: EvalTurnDriver, casos: Sequence, *, org_id: UUID, run_id: UUID,
    limite_usd: float | None, parar_no_primeiro_erro: bool = True, consolidacao: Any = None,
    agent_id: UUID | None = None, compiled_hash: str | None = None,
) -> SuiteResultado:
    """Execute the booked run and stamp it (``concluida``); a crash marks it ``falhou`` (fixed text) and re-raises."""
    try:
        resultado = await executar_suite(
            casos, driver, limite_usd=limite_usd, parar_no_primeiro_erro=parar_no_primeiro_erro,
        )
    except BaseException:
        logger.exception("agents.eval.mecanismo_run_crashed org_id=%s run_id=%s", org_id, run_id)
        store.fail_run(org_id, run_id, erro="Falha interna do executor da suíte de mecanismo.")
        raise
    harness = resultado.erro_de_harness
    if harness is not None:  # nothing was judged: the run FAILED (a harness error), it is not a 0/N score for the agent
        logger.error("agents.eval.mecanismo_harness_error org_id=%s run_id=%s %s", org_id, run_id, harness)
        store.fail_run(org_id, run_id, erro=harness[:300])
        return resultado
    store.finish_run(org_id, run_id, resultado, driver=driver.tipo)
    _registrar_consolidacao(consolidacao, resultado, org_id=org_id, agent_id=agent_id, run_id=run_id,
                            compiled_hash=compiled_hash, driver=driver.tipo)
    return resultado


def _registrar_consolidacao(
    consolidacao: Any, resultado: SuiteResultado, *, org_id: UUID, agent_id: UUID | None, run_id: UUID,
    compiled_hash: str | None, driver: str,
) -> None:
    """Fold each case's executions (one pass per passing execution, in order) into the consolidation states. Best-effort: the run
    is already stored, so a failure is logged and the backfill rebuilds it. Only LIVE runs are evidence (a fake driver proves nothing)."""
    if consolidacao is None or agent_id is None or driver != "live":
        return
    try:
        from app.studio.consolidacao_service import registrar_resultados

        registrar_resultados(
            consolidacao, org_id=org_id, agent_id=agent_id, suite="mecanismo", run_id=run_id, run_tipo="mecanismo",
            hash_atual=compiled_hash, partes=consolidacao.get_run_partes(org_id, run_id, "mecanismo"),
            resultados=[
                (cr.caso.id, [e.status for e in sorted(cr.execucoes, key=lambda e: e.indice)]) for cr in resultado.casos
            ])
    except Exception:
        logger.exception("agents.eval.mecanismo_consolidacao_falhou org_id=%s run_id=%s", org_id, run_id)


async def rodar_suite_mecanismo(
    store: Any,
    driver: EvalTurnDriver,
    *,
    org_id: UUID,
    agent_id: UUID,
    version_id: UUID,
    compiled_hash: str,
    started_by: UUID,
    limite_usd: float | None,
    parar_no_primeiro_erro: bool = True,
) -> tuple[UUID, SuiteResultado]:
    run_id, casos = iniciar_suite_mecanismo(
        store, driver, org_id=org_id, agent_id=agent_id, version_id=version_id, compiled_hash=compiled_hash,
        started_by=started_by, limite_usd=limite_usd)
    resultado = await concluir_suite_mecanismo(
        store, driver, casos, org_id=org_id, run_id=run_id, limite_usd=limite_usd,
        parar_no_primeiro_erro=parar_no_primeiro_erro)
    return run_id, resultado
