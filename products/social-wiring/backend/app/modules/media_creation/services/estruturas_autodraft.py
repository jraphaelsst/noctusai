"""Estruturas -- auto-draft from analysis (estruturas-contract.md section 8.8; owner D11; EST-5).

When a library video's classification completes, EST-2's seam
:func:`biblioteca_ingestao.registrar_depois_de_classificar` calls :func:`depois_de_classificar` (registered from THIS
file by :func:`register`). The callback only ENQUEUES the job ``estruturas.rascunho_do_viral``
(``dedupe_key = "rascunho:<viral_id>"``): a callback failure never fails the classify job and the model call happens
in the ``geracao`` worker, not inside the classifier. The pipeline is dark by construction: the seam only fires from a
classification, and classification runs only while the platform switch ``biblioteca_ingestao_habilitada`` is on.

The handler :func:`handle_rascunho` runs the shared service (:func:`estruturas_ia.criar_rascunho`) and maps its coded
refusals to the queue's vocabulary:

=============================================  ============================================================
refusal                                        outcome
=============================================  ============================================================
already has a non-archived Estrutura           return (idempotent: a redelivery or a manual draft won)
daily cap / AI budget gate / unverifiable      ``RescheduleLater`` (no retry consumed; the gate re-opens)
invalid model output (``saida_ia_invalida``)   ``DeadLetterError("saida_ia_invalida:<codigo>")`` -- the coded
                                               failure IS the record; no Estrutura, no retry (no re-spend)
no content / video gone / opt-out / no org     ``DeadLetterError(<code>)``
registry row missing / provider error          raised: the worker retries (2x), then dead-letters
=============================================  ============================================================

A draft is invisible to orgs, retrieval and generation until an admin runs ``publicar`` (the read paths filter on
``status='ativa'``; EST-1/EST-4a tests pin it).
"""
from __future__ import annotations

import logging

from noctusai_lib.domain.jobs import DeadLetterError, Job
from noctusai_lib.domain.jobs.repo import RescheduleLater

from app.modules.media_creation.services import estruturas_ia as ia
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.biblioteca_ingestao import IngestaoPorts, registrar_depois_de_classificar
from app.modules.media_creation.services.estruturas_service import EstruturaError

logger = logging.getLogger(__name__)

JOB_TYPE = "estruturas.rascunho_do_viral"
#: Retry later when the money/volume gate says "not now".
ADIAR_S = 3600

_JA_FEITO = {ia.VIRAL_JA_TEM_ESTRUTURA, ia.VIRAL_JA_TEM_RASCUNHO}
_ADIAR = {ia.LIMITE_DIARIO, ia.ORCAMENTO}
_PERMANENTES = {ia.VIRAL_NAO_ENCONTRADO, ia.VIRAL_SEM_CONTEUDO, ia.PERFIL_OPTOUT, ia.SEM_ORG, ia.CATALOGO_INVALIDO}


def _codigo(exc: EstruturaError) -> str:
    d = exc.detail
    return str(d.get("code", "")) if isinstance(d, dict) else ""


async def depois_de_classificar(ports: IngestaoPorts, viral_id: str) -> None:
    """The EST-2 seam callback: enqueue the auto-draft of a freshly analysed video that has content and no Estrutura.
    Raises nothing the seam does not already contain (it logs + records a failing callback)."""
    viral = ia.carregar_viral(ports.db, viral_id)
    if not ia.tem_conteudo(viral) or ia.ja_tem_estrutura(ports.db, viral_id):
        return
    await ports.jobs.enqueue(
        type=JOB_TYPE, payload={"viral_id": str(viral_id)}, max_retries=2, dedupe_key=f"rascunho:{viral_id}",
    )


async def executar(ports: ia.IaPorts, job: Job) -> None:
    viral_id = (job.payload or {}).get("viral_id")
    if not viral_id:
        raise DeadLetterError("payload sem viral_id")
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
            raise RescheduleLater(ADIAR_S, codigo) from exc
        if codigo == ia.SAIDA_INVALIDA:
            d = exc.detail if isinstance(exc.detail, dict) else {}
            raise DeadLetterError(f"{ia.SAIDA_INVALIDA}:{d.get('motivo', '')}:{d.get('campo') or ''}") from exc
        if codigo in _PERMANENTES:
            raise DeadLetterError(codigo) from exc
        raise  # ia_indisponivel / ia_nao_configurada / ia_falhou: transient -> the worker's retry policy


async def handle_rascunho(job: Job) -> None:
    await executar(ia.default_ports(), job)


def register() -> None:
    """Idempotent. Registers the job handler and the EST-2 seam callback (the callback registry dedupes by identity)."""
    geracao_jobs.register_handler(JOB_TYPE, handle_rascunho)
    registrar_depois_de_classificar(depois_de_classificar)


register()

__all__ = ["ADIAR_S", "JOB_TYPE", "depois_de_classificar", "executar", "handle_rascunho", "register"]
