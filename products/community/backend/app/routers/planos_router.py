"""Planos (paid tiers) router — contract §Planos.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
Reads allow both community roles (`admin` + `moderador`) — no extra gate
beyond authentication. Writes are `admin`-only via `require_admin`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.planos import (
    Plano,
    PlanoCreate,
    PlanoListResponse,
    PlanoUpdate,
)
from app.services.planos_service import PlanosService, PlanosServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planos", tags=["planos"])


@router.get("", response_model=PlanoListResponse)
async def list_planos(
    ativo: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> PlanoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    result = await service.list(ativo=ativo, page=page, page_size=page_size)
    return PlanoListResponse(**result)


@router.post("", response_model=Plano, status_code=status.HTTP_201_CREATED)
async def create_plano(
    payload: PlanoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    body = payload.model_dump()
    try:
        row = await service.create(payload=body)
    except PlanosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Plano(**row)


@router.get("/{plano_id}", response_model=Plano)
async def get_plano(
    plano_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    row = await service.get(plano_id=plano_id)
    if not row:
        raise http_error(404, "Plano não encontrado.")
    return Plano(**row)


@router.patch("/{plano_id}", response_model=Plano)
async def update_plano(
    plano_id: str,
    payload: PlanoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Plano:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update(plano_id=plano_id, payload=data)
    except PlanosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Plano não encontrado.")
    return Plano(**row)


@router.delete("/{plano_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plano(
    plano_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="excluir planos")
    client = get_user_client(token)
    service = PlanosService(client, org_id=org_id)
    ok = await service.soft_delete(plano_id=plano_id)
    if not ok:
        raise http_error(404, "Plano não encontrado.")
    return None
