"""Imóvel↔pessoa relationship reads/writes (contract
`atendimento-partes-imoveis` §4.2-§4.4):

    GET/POST/DELETE  /api/clientes/{cliente_id}/propriedades[/{id}]
    GET/POST/DELETE  /api/empresas/{empresa_id}/propriedades[/{id}]
    GET              /api/imoveis/{codigo}/proprietarios
    GET              /api/imoveis/{codigo}/interessados
    GET              /api/imoveis/{codigo}/similares

Raw-dict / `{"items","total"}` responses (house `/api/imoveis` convention).
Every `/api/imoveis/{codigo}/…` path is three segments, so none collides with
`GET /api/imoveis/{codigo}` or `/busca`; `/api/empresas/{id}/propriedades` is
three segments, so it cannot shadow the empresas router's two-segment routes.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.real_estate.matching import SCORE_MINIMO_PADRAO

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.imovel_hub import interesses_service, proprietarios_service, similares_service
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(tags=["imovel-relacionamentos"])


class PropriedadeCreateBody(StrictHttpModel):
    codigo: str = Field(min_length=1, max_length=64)


# ── propriedades (cliente / empresa) ───────────────────────────────────


@router.get("/api/clientes/{cliente_id}/propriedades")
async def listar_propriedades_cliente_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return proprietarios_service.listar_da_pessoa(client, org_id, cliente_id=cliente_id)


@router.post("/api/clientes/{cliente_id}/propriedades", status_code=status.HTTP_201_CREATED)
async def adicionar_propriedade_cliente_route(
    cliente_id: UUID,
    body: PropriedadeCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return proprietarios_service.adicionar(
        client, org_id, codigo=body.codigo, cliente_id=cliente_id,
        usuario_id=getattr(user, "id", None),
    )


@router.delete(
    "/api/clientes/{cliente_id}/propriedades/{propriedade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_propriedade_cliente_route(
    cliente_id: UUID,
    propriedade_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    proprietarios_service.remover(
        client, org_id, propriedade_id=propriedade_id, cliente_id=cliente_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/empresas/{empresa_id}/propriedades")
async def listar_propriedades_empresa_route(
    empresa_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return proprietarios_service.listar_da_pessoa(client, org_id, empresa_id=empresa_id)


@router.post("/api/empresas/{empresa_id}/propriedades", status_code=status.HTTP_201_CREATED)
async def adicionar_propriedade_empresa_route(
    empresa_id: UUID,
    body: PropriedadeCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return proprietarios_service.adicionar(
        client, org_id, codigo=body.codigo, empresa_id=empresa_id,
        usuario_id=getattr(user, "id", None),
    )


@router.delete(
    "/api/empresas/{empresa_id}/propriedades/{propriedade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_propriedade_empresa_route(
    empresa_id: UUID,
    propriedade_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> Response:
    _user, org_id = auth_parts(auth)
    proprietarios_service.remover(
        client, org_id, propriedade_id=propriedade_id, empresa_id=empresa_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── imóvel side ────────────────────────────────────────────────────────


@router.get("/api/imoveis/{codigo}/proprietarios")
async def proprietarios_do_imovel_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return proprietarios_service.do_imovel(client, org_id, codigo)


@router.get("/api/imoveis/{codigo}/interessados")
async def interessados_route(
    codigo: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return interesses_service.interessados(
        client, org_id, codigo, limite=limit, offset=offset
    )


@router.get("/api/imoveis/{codigo}/similares")
async def similares_route(
    codigo: str,
    limit: int = Query(default=similares_service.LIMITE_PADRAO, ge=1, le=similares_service.LIMITE_MAXIMO),
    score_minimo: float = Query(default=SCORE_MINIMO_PADRAO),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return similares_service.similares(
        client, org_id, codigo, limite=limit, score_minimo=score_minimo
    )


__all__ = ["router"]
