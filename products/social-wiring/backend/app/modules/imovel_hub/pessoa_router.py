"""`GET /api/clientes/{cliente_id}/resumo` — the person page payload (contract
`atendimento-partes-imoveis` §4.5). One endpoint for `/clientes/:id` AND
`/vendedores/:id` (owner D3). Card-route conventions (§0)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.imovel_hub import pessoa_service
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(prefix="/api/clientes", tags=["pessoa"])


@router.get("/{cliente_id}/resumo")
async def resumo_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return pessoa_service.resumo(client, org_id, cliente_id)


__all__ = ["router"]
