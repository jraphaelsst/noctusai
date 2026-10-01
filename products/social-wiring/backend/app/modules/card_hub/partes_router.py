"""`GET /api/clientes/{cliente_id}/partes` + `.../partes/lookup` (CONTRACT §2.1/§2.5).

Mounted by the tech-lead under `/api/clientes` (CONTRACT §10 — `card_hub/
router.py` `include_router`). ROUTE ORDER: `/partes/lookup` is declared BEFORE
anything under `/partes/{x}` (there is no such catch-all today; the order is
kept so adding one cannot shadow the literal).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user_org
from app.modules.card_hub import partes_service
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.card_hub.partes_schemas import LookupResponse, PartesResponse

router = APIRouter()


@router.get("/{cliente_id}/partes/lookup", response_model=LookupResponse)
async def lookup_documento_route(
    cliente_id: UUID,
    documento: str = Query(..., min_length=1, max_length=32),
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return partes_service.lookup_documento(
        client, org_id, cliente_id, documento=documento, atendimento_id=atendimento_id
    )


@router.get("/{cliente_id}/partes", response_model=PartesResponse)
async def listar_partes_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    resolvido, items = partes_service.listar_partes(
        client, org_id, cliente_id, atendimento_id=atendimento_id
    )
    return {"items": items, "total": len(items), "atendimento_id": resolvido}
