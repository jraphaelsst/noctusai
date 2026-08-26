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
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.imovel_hub import dados_service, documentos_service
from app.modules.imovel_hub.deps import BUCKET
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = documentos_service.TABLE

#: Give up after this many attempts. A document that cannot be read after
#: three tries is not going to become readable on the fourth, and retrying
#: forever burns vision calls on a corrupt file.
MAX_TENTATIVAS = 3

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
) -> dict:
    """Read one matrícula and record the outcome. NEVER raises."""
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        logger.warning(
            "extracao matricula: documento %s not found for org %s",
            documento_id,
            org_id,
        )
        return {"status": "erro", "erro": "documento_nao_encontrado"}

    doc = rows[0]
    if doc.get("deleted_at"):
        # Deleted between upload and this job. Reading its bytes now would be
        # work on something the user already withdrew.
        return {"status": "erro", "erro": "documento_removido"}
    if not documentos_service.deve_extrair(doc["tipo_documento"]):
        return {"status": "erro", "erro": "tipo_nao_extraivel"}

    tentativas = int(doc.get("extracao_tentativas") or 0) + 1
    _marcar(
        client,
        documento_id,
        extracao_status="processando",
        extracao_em=_now(),
        extracao_tentativas=tentativas,
    )

    try:
        blob = await storage.get(bucket=BUCKET, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("extracao matricula %s: storage read failed: %s", documento_id, exc)
        _marcar(
            client,
            documento_id,
            extracao_status="erro",
            extracao_erro=f"storage: {exc}",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "storage"}

    if blob is None:
        _marcar(
            client,
            documento_id,
            extracao_status="erro",
            extracao_erro="objeto ausente no storage",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "objeto_ausente"}

    if extractor is None:
        from noctusai_lib.integrations.documents import make_matricula_extractor

        extractor = make_matricula_extractor(real=True, org_id=str(org_id))

    campos = await extractor.extract(
        blob.data,
        mimetype=doc.get("mime_type"),
        filename=doc.get("nome_original"),
    )

    if campos.error:
        _marcar(
            client,
            documento_id,
            extracao_status="erro",
            extracao_erro=f"{campos.error}: {campos.error_message or ''}".strip(": "),
            extracao_fonte=campos.source.value,
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": campos.error}

    # Recorded whether or not it is persistable. A low-confidence read is a
    # suggestion the UI can offer next to the empty field, and the `_rotulo`
    # column lets a human check the reasoning without opening the PDF.
    _marcar(
        client,
        documento_id,
        extracao_status="ok" if campos.presente else "sem_dados",
        extracao_matricula=campos.numero_matricula,
        extracao_confianca=campos.numero_matricula_confianca.value,
        extracao_rotulo=campos.numero_matricula_rotulo,
        extracao_fonte=campos.source.value,
        extracao_erro=None,
        extracao_em=_now(),
    )

    aplicado = False
    if campos.persistable:
        aplicado = dados_service.aplicar_matricula_extraida(
            client,
            org_id,
            codigo,
            numero=campos.numero_matricula,
            documento_id=documento_id,
        )

    return {
        "status": "ok" if campos.presente else "sem_dados",
        "numero_matricula": campos.numero_matricula,
        "confianca": campos.numero_matricula_confianca.value,
        "fonte": campos.source.value,
        "tentativas": tentativas,
        "aplicado_ao_imovel": aplicado,
    }


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


async def varrer_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
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

    vistos: set[str] = set()
    alvos: list[dict] = []
    for row in list(rows) + list(nunca_iniciados):
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
