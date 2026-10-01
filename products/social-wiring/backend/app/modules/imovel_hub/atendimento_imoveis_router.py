"""`/api/clientes/{cliente_id}/atendimento-imoveis` — the imóveis an atendimento
is about (contract `atendimento-partes-imoveis` §3.1-§3.4).

Card-route conventions (§0): raw dict responses, no `{"data": …}` envelope;
lists are `{"items", "total", …}`; auth `get_current_user_org`; errors through
`AppException`. Registered via `imovel_hub.register()` (§10.4).

Every path is THREE segments under `/api/clientes`, so it cannot shadow the
two-segment `GET /api/clientes/{cliente_id}` of `clientes_router`.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.imovel_hub import atendimento_imoveis_service as svc
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(prefix="/api/clientes", tags=["atendimento-imoveis"])


class AtendimentoImovelCreateBody(StrictHttpModel):
    """§3.2 body. `origem` is `manual|campanha` only — `lead`/`negociacao` are
    system values written by `vincular_lead` / `garantir_vinculo`, so the
    Literal 422s them."""

    codigo: str = Field(min_length=1, max_length=64)
    principal: bool = False
    origem: Literal["manual", "campanha"] = "manual"
    atendimento_id: Optional[UUID] = None


@router.get("/{cliente_id}/atendimento-imoveis")
async def listar_route(
    cliente_id: UUID,
    atendimento_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.listar(client, org_id, cliente_id, atendimento_id=atendimento_id)


@router.post("/{cliente_id}/atendimento-imoveis", status_code=status.HTTP_201_CREATED)
async def adicionar_route(
    cliente_id: UUID,
    body: AtendimentoImovelCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return svc.adicionar(
        client,
        org_id,
        cliente_id,
        codigo=body.codigo,
        principal=body.principal,
        origem=body.origem,
        atendimento_id=body.atendimento_id,
        usuario_id=getattr(user, "id", None),
    )


@router.put("/{cliente_id}/atendimento-imoveis/{item_id}/principal")
async def principal_route(
    cliente_id: UUID,
    item_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.definir_principal(client, org_id, cliente_id, item_id)


@router.delete(
    "/{cliente_id}/atendimento-imoveis/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_route(
    cliente_id: UUID,
    item_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    svc.remover(client, org_id, cliente_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
