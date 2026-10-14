"""Org-level Favorecidos registry (migration 251).

  GET    /api/card-hub/favorecidos?q=&ativo=      masked list  {items:[...]}
  GET    /api/card-hub/favorecidos/{id}           full record (write role) / masked (read-only)
  POST   /api/card-hub/favorecidos                create (write role)
  PATCH  /api/card-hub/favorecidos/{id}           update (write role)
  DELETE /api/card-hub/favorecidos/{id}           soft: ativo=false (write role)
  PUT    /api/card-hub/atendimentos/{atendimento_id}/favorecidos/selecao
                                         link a registry entry to the card

A DISTINCT `/api/card-hub` prefix, not `/api/clientes/favorecidos`: a literal
1-segment path under `/api/clientes` structurally collides with
`clientes_router`'s bare `/{cliente_id}` (see `router.py`'s header).

🔴 LGPD: values are never logged; the list is masked; the full record and every
write need a write role (see `favorecidos_service`).
Auth is covered by `test_auth_boundary_favorecidos.py` (strict 401).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_core_client, get_current_user_org
from app.modules.card_hub import favorecidos_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client

router = APIRouter(tags=["favorecidos"])


class FavorecidoRegistroCreateBody(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=255)
    tipo_pessoa: Optional[str] = Field(default=None, max_length=2)
    cpf_cnpj: Optional[str] = Field(default=None, max_length=32)
    banco: Optional[str] = Field(default=None, max_length=120)
    agencia: Optional[str] = Field(default=None, max_length=32)
    conta: Optional[str] = Field(default=None, max_length=32)
    tipo_conta: Optional[str] = Field(default=None, max_length=16)
    pix_tipo: Optional[str] = Field(default=None, max_length=16)
    pix: Optional[str] = Field(default=None, max_length=140)
    corretor_id: Optional[UUID] = None


class FavorecidoRegistroPatchBody(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tipo_pessoa: Optional[str] = Field(default=None, max_length=2)
    cpf_cnpj: Optional[str] = Field(default=None, max_length=32)
    banco: Optional[str] = Field(default=None, max_length=120)
    agencia: Optional[str] = Field(default=None, max_length=32)
    conta: Optional[str] = Field(default=None, max_length=32)
    tipo_conta: Optional[str] = Field(default=None, max_length=16)
    pix_tipo: Optional[str] = Field(default=None, max_length=16)
    pix: Optional[str] = Field(default=None, max_length=140)
    corretor_id: Optional[UUID] = None
    ativo: Optional[bool] = None


class FavorecidoSelecaoBody(StrictHttpModel):
    favorecido_id: UUID
    intermediario_id: Optional[UUID] = None


@router.get("/api/card-hub/favorecidos")
async def list_favorecidos_route(
    q: Optional[str] = Query(default=None, max_length=120),
    ativo: Optional[bool] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.listar(client, org_id, q=q, ativo=ativo)


@router.get("/api/card-hub/favorecidos/{favorecido_id}")
async def get_favorecido_route(
    favorecido_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    request: Request = None,
) -> dict:
    user, org_id = auth_parts(auth)
    completo = svc.tem_papel_de_escrita(get_core_client(), auth, request)
    return svc.obter(client, org_id, favorecido_id, completo=completo)


@router.post("/api/card-hub/favorecidos", status_code=201)
async def create_favorecido_registro_route(
    body: FavorecidoRegistroCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    request: Request = None,
) -> dict:
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    svc.exigir_escrita(get_core_client(), auth, request)
    return svc.criar(client, org_id, valores=body.model_dump(), usuario_id=usuario_id)


@router.patch("/api/card-hub/favorecidos/{favorecido_id}")
async def patch_favorecido_registro_route(
    favorecido_id: UUID,
    body: FavorecidoRegistroPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    request: Request = None,
) -> dict:
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    svc.exigir_escrita(get_core_client(), auth, request)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return svc.atualizar(
        client, org_id, favorecido_id, valores=valores, usuario_id=usuario_id
    )


@router.delete("/api/card-hub/favorecidos/{favorecido_id}", status_code=204)
async def delete_favorecido_registro_route(
    favorecido_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    request: Request = None,
):
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    svc.exigir_escrita(get_core_client(), auth, request)
    svc.desativar(client, org_id, favorecido_id, usuario_id=usuario_id)


@router.put("/api/card-hub/atendimentos/{atendimento_id}/favorecidos/selecao")
async def put_favorecido_selecao_route(
    atendimento_id: UUID,
    body: FavorecidoSelecaoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return svc.selecionar_para_card(
        client, org_id, atendimento_id,
        favorecido_id=body.favorecido_id, intermediario_id=body.intermediario_id,
        usuario_id=getattr(user, "id", None),
    )


__all__ = ["router"]
