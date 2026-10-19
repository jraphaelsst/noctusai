"""Run the mechanism suite of one agent version and record it (Julia v2 A-EVAL).

The orchestration the (platform-admin) trigger calls: load the active ``mecanismo`` cases, drive them through
the injected :class:`EvalTurnDriver`, persist the per-execution outcomes, and stamp the run. The run is stamped
with the driver's ``tipo``; only ``live`` runs can open the publish gate (``eval_mecanismo.decidir_portao``).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.studio.eval_driver import EvalTurnDriver
from app.studio.eval_mecanismo import SuiteResultado, executar_suite

logger = logging.getLogger(__name__)

__all__ = ["SuiteVazia", "DriverSemTipo", "rodar_suite_mecanismo"]

_TIPOS = ("live", "fake")


class SuiteVazia(RuntimeError):
    """The agent has no active mecanismo case: there is nothing to run (and nothing to approve)."""


class DriverSemTipo(RuntimeError):
    """The driver does not declare ``tipo`` in ('live','fake'): refuse rather than guess (fail closed)."""


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
    tipo = getattr(driver, "tipo", None)
    if tipo not in _TIPOS:
        raise DriverSemTipo("driver.tipo must be 'live' or 'fake'")
    casos = store.list_active_cases(org_id, agent_id)
    if not casos:
        raise SuiteVazia("no active mecanismo case")
    run_id = store.start_run(
        org_id, agent_id, version_id, compiled_hash=compiled_hash, driver=tipo,
        limite_usd=limite_usd, started_by=started_by, total_casos=len(casos),
    )
    try:
        resultado = await executar_suite(
            casos, driver, limite_usd=limite_usd, parar_no_primeiro_erro=parar_no_primeiro_erro,
        )
    except BaseException:
        logger.exception("agents.eval.mecanismo_run_crashed org_id=%s run_id=%s", org_id, run_id)
        store.fail_run(org_id, run_id, erro="Falha interna do executor da suíte de mecanismo.")
        raise
    store.finish_run(org_id, run_id, resultado, driver=tipo)
    return run_id, resultado
