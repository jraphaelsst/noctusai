"""Recover Cartão CNPJ extractions that were started and never finished —
D3, now built on the shared `app.services.extracao_varredura` (S2 contract
`sw-negociacao-extracao-contract.md` §E3.3 — the recurrence-rule
formalization: this was the FOURTH hand-rolled sweep of the exact same
shape, and shipping a fifth was forbidden).

`extracao_status` moves to `processando` before the work and to a terminal
value after it. If the process dies in between, nothing ever moves it
again; this sweep is the recovery, retrying a FAILED read at most
`MAX_RETENTATIVAS_ERRO` times before leaving it `erro` for a human.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.storage import StorageBackend

from app.modules.empresas import documentos_service, extracao_service
from app.services import extracao_varredura

logger = logging.getLogger(__name__)

STALE_APOS = extracao_varredura.STALE_APOS

_COLUNAS_VARREDURA = "id, org_id, empresa_id, tipo_documento, extracao_status, extracao_tentativas, extracao_em, created_at"


def _config(extractor_factory: Optional[Any]) -> extracao_varredura.SweepConfig:
    return extracao_varredura.SweepConfig(
        table=documentos_service.TABLE,
        owner_col="empresa_id",
        colunas=_COLUNAS_VARREDURA,
        extrair_fn=extracao_service.extrair_cartao,
        max_tentativas=extracao_service.MAX_TENTATIVAS,
        extractor_factory=extractor_factory,
    )


async def varrer_extracoes_pendentes(
    client: Any,
    storage: StorageBackend,
    *,
    extractor_factory: Optional[Any] = None,
    notification_service: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    return await extracao_varredura.varrer(
        client, storage, _config(extractor_factory),
        notification_service=notification_service, limite=limite,
    )


__all__ = ["STALE_APOS", "varrer_extracoes_pendentes"]
