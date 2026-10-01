"""`/api/clientes/{cliente_id}/interesses` — the imóveis a cliente is interested
in (contract `atendimento-partes-imoveis` §4.1). Card-route conventions (§0).

`lead` and `roteiro` origens are system-only: the body's Literal 422s them.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.imovel_hub import interesses_service as svc
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(prefix="/api/clientes", tags=["interesses"])


class InteresseCreateBody(StrictHttpModel):
    codigo: str = Field(min_length=1, max_length=64)
    origem: Literal["manual", "campanha", "permuta"] = "manual"


@router.get("/{cliente_id}/interesses")
async def listar_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.listar(client, org_id, cliente_id)


@router.post("/{cliente_id}/interesses", status_code=status.HTTP_201_CREATED)
async def adicionar_route(
    cliente_id: UUID,
    body: InteresseCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return svc.adicionar(
        client,
        org_id,
        cliente_id,
        codigo=body.codigo,
        origem=body.origem,
        usuario_id=getattr(user, "id", None),
    )


@router.delete(
    "/{cliente_id}/interesses/{interesse_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_route(
    cliente_id: UUID,
    interesse_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    svc.remover(client, org_id, cliente_id, interesse_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
