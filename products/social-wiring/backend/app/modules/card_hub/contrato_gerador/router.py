"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/{geracao,gerar}` — F5.

A separate file, `include_router`'d into `card_hub/router.py`'s `router` with
one line (same layout `negociacao_estruturada_router.py` uses), so every path
inherits `/api/clientes` and registers once in card_hub's existing
`ModuleRegistration`. Both paths are 4 segments ending in a literal distinct
from `versoes`, so they cannot shadow or be shadowed by the contratos routes.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_contrato_gerador.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.contrato_gerador import service
from app.modules.card_hub.contrato_gerador.deps import (
    get_complementos_contrato,
    get_contrato_docx_adapter,
    get_politica_contrato,
)
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend

router = APIRouter()


class GerarContratoBody(StrictHttpModel):
    #: Date printed as the signing date; defaults to today in São Paulo.
    assinatura_data: Optional[date] = None


@router.get("/{cliente_id}/contratos/{contrato_id}/geracao")
async def get_contrato_geracao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    complementos=Depends(get_complementos_contrato),
    politica=Depends(get_politica_contrato),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.obter_geracao(
        client,
        org_id,
        cliente_id,
        contrato_id,
        usuario_id=getattr(user, "id", None),
        complementos=complementos,
        politica=politica,
    )


@router.post("/{cliente_id}/contratos/{contrato_id}/gerar", status_code=201)
async def post_contrato_gerar_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: Optional[GerarContratoBody] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    adapter=Depends(get_contrato_docx_adapter),
    complementos=Depends(get_complementos_contrato),
    politica=Depends(get_politica_contrato),
) -> dict:
    user, org_id = auth_parts(auth)
    return await service.gerar(
        client,
        storage,
        adapter,
        org_id,
        cliente_id,
        contrato_id,
        assinatura=body.assinatura_data if body else None,
        usuario_id=getattr(user, "id", None),
        complementos=complementos,
        politica=politica,
    )


__all__ = ["GerarContratoBody", "router"]
