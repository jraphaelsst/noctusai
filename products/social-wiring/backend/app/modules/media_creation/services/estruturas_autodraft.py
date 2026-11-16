"""Estruturas -- auto-draft from analysis (estruturas-contract.md section 8.8; owner D11; EST-5).

When a library video's classification completes, EST-2's seam
:func:`biblioteca_ingestao.registrar_depois_de_classificar` calls :func:`depois_de_classificar` (registered from THIS
file by :func:`register`). The callback only ENQUEUES the job ``estruturas.rascunho_do_viral``
(``dedupe_key = "rascunho:<viral_id>"``): a callback failure never fails the classify job and the model call happens
in the ``geracao`` worker, not inside the classifier.

Dark by construction AND by an explicit check: the seam only fires from a classification (which runs only while the
platform switch ``biblioteca_ingestao_habilitada`` is on), and BOTH the callback and the handler read the switch first
(OFF / unreadable: no enqueue; a queued job waits for the next UTC day).

Backlog control (a burst of classifications must not become a burst of model calls):

* the callback enqueues only while ``attempts today + queued/running jobs < estruturas_autodraft_dia`` (cheap counts),
  so the pending backlog never exceeds one day's cap; a video classified while the cap is full is simply not
  auto-drafted (an admin can use ``POST /estruturas/a-partir-do-viral``). NOC-REMEDIATE[autodraft-daily-sweep]: a
  once-a-day sweep that enqueues at most the cap's worth of analysed videos without a draft belongs in
  ``biblioteca_scheduler`` (FIX-1's file; a new cron + its poll-budget declaration) -- before switch-on;
* the handler reschedules a cap / budget / switch refusal to the NEXT UTC midnight + 0..3600 s of jitter (never
  +1 h), so each queued job is claimed at most once per UTC day while the gate is closed;
* a job older than :data:`IDADE_MAXIMA` and a provider out of credit dead-letter with a coded reason.

The handler :func:`handle_rascunho` runs the shared service (:func:`estruturas_ia.criar_rascunho`) and maps its coded
refusals to the queue's vocabulary:

=============================================  ============================================================
refusal                                        outcome
=============================================  ============================================================
already has a non-archived Estrutura           return (idempotent: a redelivery or a manual draft won)
switch off / daily cap / AI budget gate /      ``RescheduleLater`` to the next UTC midnight + jitter
invalid model output (``saida_ia_invalida``)   ``DeadLetterError("saida_ia_invalida:<codigo>:<campo>")`` -- the
                                               coded failure IS the record; no Estrutura, no retry (no re-spend)
provider out of credit / job older than 7 d    ``DeadLetterError(<code>)``
no content / video gone / opt-out / no org     ``DeadLetterError(<code>)``
registry row missing / provider error          raised: the worker retries (2x), then dead-letters
=============================================  ============================================================

A draft is invisible to orgs, retrieval and generation until an admin runs ``publicar`` (the read paths filter on
``status='ativa'``; EST-1/EST-4a tests pin it), and ``publicar`` of an unreviewed AI draft is refused.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

import anyio.to_thread

from noctusai_lib.domain.jobs import DeadLetterError, Job
from noctusai_lib.domain.jobs.repo import RescheduleLater

from app.modules.media_creation.services import estruturas_ia as ia
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.biblioteca_ingestao import IngestaoPorts, registrar_depois_de_classificar
from app.modules.media_creation.services.estruturas_service import EstruturaError

logger = logging.getLogger(__name__)

JOB_TYPE = "estruturas.rascunho_do_viral"
#: A queued derivation older than this is stale (the video may have been purged / the data re-classified): dead-letter.
IDADE_MAXIMA = timedelta(days=7)

_JA_FEITO = {ia.VIRAL_JA_TEM_ESTRUTURA, ia.VIRAL_JA_TEM_RASCUNHO}
#: The gate is closed for today: wait for the next UTC day (+ jitter), consuming no retry.
_ADIAR = {ia.LIMITE_DIARIO, ia.ORCAMENTO, ia.BIBLIOTECA_DESLIGADA, ia.LIMITE_NAO_VERIFICAVEL}
_PERMANENTES = {
    ia.VIRAL_NAO_ENCONTRADO, ia.VIRAL_SEM_CONTEUDO, ia.PERFIL_OPTOUT, ia.SEM_ORG, ia.CATALOGO_INVALIDO, ia.SEM_CREDITO_PROVEDOR,
}


def _codigo(exc: EstruturaError) -> str:
    d = exc.detail
    return str(d.get("code", "")) if isinstance(d, dict) else ""


def _pendentes_padrao(ports: Any) -> int:
    """Queued, running and failed-awaiting-retry derivation jobs (the ``jobs`` table of the product schema)."""
    res = (
        ports.db.table("jobs").select("id", count="exact").eq("type", JOB_TYPE).in_("status", ["pending", "running", "failed"])
        .limit(1).execute()
    )
    return res.count if getattr(res, "count", None) is not None else len(res.data or [])


def make_callback(
    *, habilitada: Callable[[], bool] = geracao_jobs.read_ingestao_habilitada,
    pendentes: Callable[[Any], int] = _pendentes_padrao,
) -> Callable[[IngestaoPorts, str], Any]:
    """The EST-2 seam callback, with its two readings (switch, queue depth) injectable for tests."""

    def verificar(ports: IngestaoPorts, viral_id: str) -> bool:
        """Sync part (runs in a worker thread): True = enqueue."""
        try:
            if not habilitada():
                return False
        except Exception as exc:  # noqa: BLE001 - an unreadable switch reads as OFF (fail closed)
            logger.error("estruturas.rascunho_do_viral: chave de ingestão ilegível (%s)", type(exc).__name__)
            return False
        viral = ia.carregar_viral(ports.db, viral_id)
        if not ia.tem_conteudo(viral) or ia.ja_tem_estrutura(ports.db, viral_id):
            return False
        try:
            core = ports.ledger_factory() if getattr(ports, "ledger_factory", None) else None
            if core is None:
                raise RuntimeError("sem cliente core")
            carga = ia.contar_tentativas_do_dia(core, ports.clock()) + pendentes(ports)
        except Exception as exc:  # noqa: BLE001 - unmeasurable load: do not enqueue (fail closed), logged
            logger.error("estruturas.rascunho_do_viral: carga do dia não medida (%s); sem enfileirar", type(exc).__name__)
            return False
        return carga < int(ports.cfg.estruturas_autodraft_dia)

    async def depois_de_classificar(ports: IngestaoPorts, viral_id: str) -> None:
        """Enqueue the auto-draft of a freshly analysed video that has content and no Estrutura, while today's
        capacity (attempts + queue) is below the cap. Raises nothing the seam does not already contain."""
        if not await anyio.to_thread.run_sync(verificar, ports, viral_id):
            return
        await ports.jobs.enqueue(
            type=JOB_TYPE, payload={"viral_id": str(viral_id)}, max_retries=2, dedupe_key=f"rascunho:{viral_id}",
        )

    return depois_de_classificar


depois_de_classificar = make_callback()


async def executar(ports: ia.IaPorts, job: Job) -> None:
    viral_id = (job.payload or {}).get("viral_id")
    if not viral_id:
        raise DeadLetterError("payload sem viral_id")
    if ports.clock() - job.created_at > IDADE_MAXIMA:
        raise DeadLetterError("job_expirado")
    try:
        await ia.criar_rascunho(
            ports, str(viral_id), origem=ia.ORIGEM_AUTO, ator_id=None, ator_tipo="sistema_ia",
        )
    except EstruturaError as exc:
        codigo = _codigo(exc)
        if codigo in _JA_FEITO:
            logger.info("estruturas.rascunho_do_viral: viral=%s já tem estrutura (%s); nada a fazer", viral_id, codigo)
            return
        if codigo in _ADIAR:
            raise RescheduleLater(
                ia.segundos_ate_o_proximo_dia(ports.clock(), ports.jitter()), codigo,
            ) from exc
        if codigo == ia.SAIDA_INVALIDA:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            raise DeadLetterError(f"{ia.SAIDA_INVALIDA}:{d.get('motivo', '')}:{d.get('campo') or ''}") from exc
        if codigo in _PERMANENTES:
            raise DeadLetterError(codigo) from exc
        raise  # ia_indisponivel / ia_nao_configurada / ia_falhou: transient -> the retry policy


async def handle_rascunho(job: Job) -> None:
    await executar(ia.default_ports(), job)


def register() -> None:
    """Idempotent. Registers the job handler and the EST-2 seam callback (the callback registry dedupes by identity)."""
    geracao_jobs.register_handler(JOB_TYPE, handle_rascunho)
    registrar_depois_de_classificar(depois_de_classificar)


register()

__all__ = [
    "IDADE_MAXIMA", "JOB_TYPE", "depois_de_classificar", "executar", "handle_rascunho", "make_callback", "register",
]
