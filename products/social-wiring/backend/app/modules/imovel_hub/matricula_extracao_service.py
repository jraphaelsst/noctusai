"""Read the número de matrícula off an uploaded certidão, and feed it in.

The flow the user asked for: a matrícula is uploaded, the system reads the
PDF, finds the número de matrícula, and fills our field with it.

WHERE THE WORK ACTUALLY HAPPENS
-------------------------------
Almost nowhere here. `noctusai_lib.integrations.documents` owns the ladder
(PDF text layer → rasterize→vision) and the parser (`find_matricula`, which
is mostly negative logic: a matrícula is wall-to-wall numbers, so labels are
the only signal, and a match after a body marker belongs to a DIFFERENT
property). This module owns only the bookkeeping around them — which is
still the part that decides whether a failure is visible.

🔴 EVERY FAILURE PATH ENDS IN A RECORDED STATUS
-----------------------------------------------
This runs detached from the request that triggered it. An exception raised
here surfaces NOWHERE: no user sees it, no response carries it, and the
document sits in `processando` forever with a field that never fills in. So
`extrair()` never raises — every outcome, including the ugly ones, is
written to `extracao_status`.

That covers everything except the one case it cannot: the process dying
mid-read. `varrer_pendentes()` is the answer to that, and it is why
`pendente` is stamped at UPLOAD time rather than by this job — a job that
never started is then indistinguishable from one that did, and both are
recoverable.

🔴 lesson G6 (2026-09-28): this used to stamp the TERMINAL `extracao_
status` (`ok`/`sem_dados`) in the SAME write as the reading, then call
`campos_svc.aplicar` in a `try` that only LOGGED the exception — the
already-written `ok` stood even when the apply failed, so a transient DB
error left the field never filled with nothing to retry (the sweep never
revisits an `ok` row). Now built on the shared `app.services.extracao_job`
runner (see that module's own docstring for the other two siblings this
formalizes): the reading is persisted WITHOUT a terminal status, the apply
runs inside the runner's own try, and the terminal status is written only
after it succeeds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from app.modules.imovel_hub import documentos_service
from app.modules.imovel_hub.deps import BUCKET
from app.services import extracao_job, extracao_retentativa, table_reads

logger = logging.getLogger(__name__)

TABLE = documentos_service.TABLE

#: Give up after this many attempts — the first plus D3's two automatic
#: retries (`app.services.extracao_retentativa`). A document that cannot be
#: read after three tries is not going to become readable on the fourth, and
#: retrying forever burns vision calls on a corrupt file.
MAX_TENTATIVAS = extracao_retentativa.MAX_TENTATIVAS

#: A document stuck in a non-terminal state longer than this was orphaned by
#: a process that died. Generous enough that a slow vision pass is never
#: mistaken for a dead one.
STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _marcar(client: Any, documento_id: UUID, **updates: Any) -> None:
    _t(client, TABLE).update(updates).eq("id", str(documento_id)).execute()


async def extrair(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    codigo: str,
    documento_id: UUID,
    *,
    extractor: Optional[Any] = None,
    notificador: Optional[Any] = None,
) -> dict:
    """Read one matrícula and record the outcome. NEVER raises.

    🔴 D1 (owner, 2026-09-22) REPLACES the old "text-layer `alta` only" rule:
    any labelled reading (`alta` OR `baixa` — a vision read is `baixa` by
    construction, see the seed extractor) is applied through
    `campos_extraidos_service.aplicar`. That is safe now because an applied
    machine value is never trusted unattended any more — it stays
    machine-pending until a human validates it at contract generation (D2),
    and it never overwrites anything (a disagreement is a conflict).
    `nenhuma` (no label, or heading numbers that disagree) is still never
    written: there is no reading to validate.
    """
    if extractor is None:
        from noctusai_lib.integrations.documents import make_matricula_extractor

        from app.services.api_keys_store import resolve_vision_provider

        # Same per-org manual switch `deps._build_matricula_extractor`
        # applies — this fallback used to omit `provider=`, so an org's
        # explicit choice was ignored on this path.
        extractor = make_matricula_extractor(
            real=True, org_id=str(org_id), provider=resolve_vision_provider(str(org_id))
        )

    async def _ler(blob_bytes: bytes, doc: dict) -> Any:
        return await extractor.extract(
            blob_bytes, mimetype=doc.get("mime_type"), filename=doc.get("nome_original"),
        )

    async def _processar(campos: Any, doc: dict) -> dict:
        # Recorded whether or not it is persistable, and WITHOUT the
        # terminal status (lesson G6) — a low-confidence read is a
        # suggestion the UI can offer next to the empty field, and the
        # `_rotulo` column lets a human check the reasoning without
        # opening the PDF.
        extracao_job.marcar(
            client, TABLE, documento_id,
            extracao_matricula=campos.numero_matricula,
            extracao_confianca=campos.numero_matricula_confianca.value,
            extracao_rotulo=campos.numero_matricula_rotulo,
        )

        aplicado = False
        conflito = False
        if campos.persistable or campos.sugestao:
            # No try here — an exception now propagates to the runner's own
            # try/except, which ends the job in `erro` (lesson G6: this used
            # to only LOG the exception, leaving an already-written `ok`
            # standing with nothing actually applied).
            resultado = campos_svc.aplicar(
                client,
                org_id,
                codigo,
                "numero_matricula",
                campos.numero_matricula,
                origem="matricula",
                documento_id=documento_id,
                confianca=campos.numero_matricula_confianca.value,
                fonte_tabela=campos_svc.FONTE_DOCUMENTOS,
                fonte_id=documento_id,
            )
            aplicado = resultado.preenchido
            if resultado.conflito is not None:
                conflito = True
                await campos_svc.notificar(
                    client, org_id, codigo, [resultado.conflito], notificador
                )

        return {
            "status": "ok" if campos.presente else "sem_dados",
            "numero_matricula": campos.numero_matricula,
            "confianca": campos.numero_matricula_confianca.value,
            "fonte": campos.source.value,
            "aplicado_ao_imovel": aplicado,
            "conflito_aberto": conflito,
        }

    config = extracao_job.ExtractionJobConfig(
        table=TABLE,
        bucket=BUCKET,
        deve_extrair=documentos_service.deve_extrair,
        ler=_ler,
        leitura_erro=lambda campos: campos.error,
        leitura_erro_mensagem=lambda campos: campos.error_message,
        leitura_fonte=lambda campos: campos.source.value,
        erro_aplicar_codigo="aplicar_campos",
        processar=_processar,
    )
    return await extracao_job.executar(client, storage, org_id, documento_id, config)


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


#: NOC-REMEDIATE[dry-extracao-varredura]: this sweep's candidate-selection
#: shape (stale non-terminal / never-started / retryable-error) is now
#: shared in `app.services.extracao_varredura` (S2 contract `sw-negociacao-
#: extracao-contract.md` §E3.3 — `empresas.sweep_service` and
#: `card_hub.negociacao_extracao_service` already migrated). Porting this
#: one needs its own review (its candidate query is keyed differently —
#: matrícula-extraction-specific columns) — 2026-09-25.
async def varrer_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
    notificador: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    """Re-run extractions that were started and never finished.

    🔴 WHY THIS EXISTS. `extracao_status` moves to `processando` before the
    work and to a terminal value after it. If the process dies in between — a
    deploy, an OOM kill, a container restart — nothing ever moves it again.
    The document sits there, the field never fills, and NOTHING SURFACES.
    The same is true of `pendente` when the background task was never
    scheduled at all.

    Both are recovered by the same query, which is the reason `pendente` is
    stamped at upload time.
    """
    cutoff = _stale_cutoff()
    rows = (
        _t(client, TABLE)
        .select("*")
        .in_("extracao_status", list(_ESTADOS_NAO_TERMINAIS))
        .is_("deleted_at", "null")
        .lt("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []

    # A `pendente` row whose job never ran has a NULL `extracao_em`, which the
    # `lt` above filters out — so they are collected separately rather than
    # left permanently invisible.
    nunca_iniciados = (
        _t(client, TABLE)
        .select("*")
        .eq("extracao_status", "pendente")
        .is_("deleted_at", "null")
        .is_("extracao_em", "null")
        .limit(limite)
        .execute()
    ).data or []

    # D3 (migration 154): a FAILED read is retried too — at most twice
    # (`extracao_tentativas < MAX_TENTATIVAS`), and only when the failure is
    # one a retry can fix (an exhausted provider account, a rate limit — not
    # an empty PDF). `lt(cutoff)` spaces the retry from the failure.
    falhos = [
        r
        for r in (
            _t(client, TABLE)
            .select("*")
            .eq("extracao_status", "erro")
            .is_("deleted_at", "null")
            .lt("extracao_tentativas", MAX_TENTATIVAS)
            .lt("extracao_em", cutoff)
            .limit(limite)
            .execute()
        ).data
        or []
        if extracao_retentativa.retentavel(
            extracao_retentativa.codigo_de_erro(r.get("extracao_erro"))
        )
    ]

    vistos: set[str] = set()
    alvos: list[dict] = []
    for row in list(rows) + list(nunca_iniciados) + falhos:
        if row["id"] in vistos:
            continue
        vistos.add(row["id"])
        alvos.append(row)

    reprocessados = 0
    desistidos = 0
    for row in alvos:
        if int(row.get("extracao_tentativas") or 0) >= MAX_TENTATIVAS:
            # Given up on, LOUDLY: a terminal `erro` with a reason, never a
            # row silently left in `processando` for the next sweep to
            # rediscover forever.
            _marcar(
                client,
                UUID(str(row["id"])),
                extracao_status="erro",
                extracao_erro=(
                    f"desistiu apos {MAX_TENTATIVAS} tentativas sem sucesso"
                ),
                extracao_em=_now(),
            )
            desistidos += 1
            continue

        org_id = UUID(str(row["org_id"]))
        extractor = extractor_factory(str(org_id)) if extractor_factory else None
        await extrair(
            client,
            storage,
            org_id,
            row["codigo"],
            UUID(str(row["id"])),
            extractor=extractor,
            notificador=notificador,
        )
        reprocessados += 1

    return {
        "encontrados": len(alvos),
        "reprocessados": reprocessados,
        "desistidos": desistidos,
    }


__all__ = [
    "MAX_TENTATIVAS",
    "STALE_APOS",
    "extrair",
    "varrer_pendentes",
]
