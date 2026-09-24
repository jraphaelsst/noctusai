"""Recover Cartão CNPJ extractions that were started and never finished —
D3, mirroring `identidade_extracao_service.varrer_extracoes_pendentes` /
`{card_hub,imovel_hub}.extracao_scheduler`'s own shape verbatim.

`extracao_status` moves to `processando` before the work and to a terminal
value after it. If the process dies in between, nothing ever moves it
again; this sweep is the recovery, retrying a FAILED read at most
`MAX_RETENTATIVAS_ERRO` times before leaving it `erro` for a human.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.empresas import documentos_service, extracao_service
from app.services import table_reads

logger = logging.getLogger(__name__)

STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")
_COLUNAS_VARREDURA = "id, org_id, empresa_id, tipo_documento, extracao_status, extracao_tentativas, extracao_em, created_at"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _stale_cutoff() -> str:
    return (datetime.now(timezone.utc) - STALE_APOS).isoformat()


def _candidatos(client: Any, limite: int) -> list[dict]:
    cutoff = _stale_cutoff()
    base = lambda: (  # noqa: E731
        _t(client, documentos_service.TABLE)
        .select(_COLUNAS_VARREDURA)
        .is_("deleted_at", "null")
    )
    parados = (
        base()
        .in_("extracao_status", list(_ESTADOS_NAO_TERMINAIS))
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    nunca_iniciados = (
        base()
        .eq("extracao_status", "pendente")
        .is_("extracao_em", "null")
        .lte("created_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    com_erro = (
        base()
        .eq("extracao_status", "erro")
        .lt("extracao_tentativas", extracao_service.MAX_TENTATIVAS)
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    vistos: set[str] = set()
    linhas: list[dict] = []
    for row in [*parados, *nunca_iniciados, *com_erro]:
        chave = str(row["id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(row)
    linhas.sort(key=lambda r: r.get("extracao_em") or r.get("created_at") or "")
    return linhas[:limite]


async def varrer_extracoes_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
    notification_service: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    rows = _candidatos(client, limite)

    retomados = 0
    esgotados = 0
    falhas = 0

    for row in rows:
        documento_id = UUID(str(row["id"]))
        tentativas = int(row.get("extracao_tentativas") or 0)

        if tentativas >= extracao_service.MAX_TENTATIVAS:
            _t(client, documentos_service.TABLE).update(
                {
                    "extracao_status": "erro",
                    "extracao_erro": (
                        f"extração abandonada após {tentativas} tentativas "
                        f"(limite {extracao_service.MAX_TENTATIVAS})"
                    ),
                    "extracao_em": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", str(documento_id)).execute()
            esgotados += 1
            continue

        try:
            org_id = UUID(str(row["org_id"]))
            empresa_id = UUID(str(row["empresa_id"]))
            tipo_documento = str(row.get("tipo_documento") or "")
            extractor = (
                extractor_factory(str(org_id), tipo_documento)
                if extractor_factory
                else None
            )
            await extracao_service.extrair_cartao(
                client, storage, org_id, empresa_id, documento_id,
                extractor=extractor,
                notification_service=notification_service,
            )
            retomados += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.warning("empresas sweep: documento %s failed: %s", documento_id, exc)
            falhas += 1

    if rows:
        logger.info(
            "empresas extracao sweep: %d candidate(s), %d retried, %d exhausted, %d failed",
            len(rows), retomados, esgotados, falhas,
        )
    return {
        "encontrados": len(rows),
        "retomados": retomados,
        "esgotados": esgotados,
        "falhas": falhas,
    }


__all__ = ["STALE_APOS", "varrer_extracoes_pendentes"]
