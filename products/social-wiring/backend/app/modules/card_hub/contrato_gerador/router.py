"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/{geracao,gerar}` and
`POST /api/clientes/{cliente_id}/contratos/gerar` (start one) — F5.

A separate file, `include_router`'d into `card_hub/router.py`'s `router` with
one line (same layout `negociacao_estruturada_router.py` uses), so every path
inherits `/api/clientes` and registers once in card_hub's existing
`ModuleRegistration`. Both paths are 4 segments ending in a literal distinct
from `versoes`, so they cannot shadow or be shadowed by the contratos routes.
The 3-segment start route ends in the literal `gerar`; the only other
3-segment POST is `/{cliente_id}/contratos` itself, and `{contrato_id}` 3rd
segments are PATCH/DELETE only (and UUID-typed) — no overlap.

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
    get_contrato_docx_adapter,
    get_politica_contrato,
)
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend

router = APIRouter()


class GerarContratoBody(StrictHttpModel):
    #: Dates the instrument. Absent falls back to the date stored on the
    #: contract (migration 114), then to today in São Paulo — see
    #: `service.data_assinatura`.
    assinatura_data: Optional[date] = None


@router.post("/{cliente_id}/contratos/gerar", status_code=201)
async def post_contrato_iniciar_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    politica=Depends(get_politica_contrato),
) -> dict:
    """The card's "Gerar contrato" button: creates the contract to generate
    and returns `{contrato, geracao}` — see `service.iniciar`."""
    user, org_id = auth_parts(auth)
    return service.iniciar(
        client,
        org_id,
        cliente_id,
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )


@router.get("/{cliente_id}/contratos/{contrato_id}/geracao")
async def get_contrato_geracao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    politica=Depends(get_politica_contrato),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.obter_geracao(
        client,
        org_id,
        cliente_id,
        contrato_id,
        usuario_id=getattr(user, "id", None),
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
        politica=politica,
    )


__all__ = ["GerarContratoBody", "router"]
