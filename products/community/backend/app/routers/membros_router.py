"""Membros router — contract §Membros.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
Reads allow both community roles — no extra gate. Writes are
`admin`-only via `require_admin`.
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
from app.schemas.membros import (
    Membro,
    MembroCreate,
    MembroListResponse,
    MembroStatusUpdate,
    MembroUpdate,
)
from app.services.membros_service import MembrosService, MembrosServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/membros", tags=["membros"])


@router.get("", response_model=MembroListResponse)
async def list_membros(
    status: str | None = Query(default=None),
    plano_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    busca: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> MembroListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    result = await service.list(
        status=status, plano_id=plano_id, tag=tag, busca=busca,
        page=page, page_size=page_size,
    )
    return MembroListResponse(**result)


@router.post("", response_model=Membro, status_code=status.HTTP_201_CREATED)
async def create_membro(
    payload: MembroCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Membro:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar membros")
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    try:
        row = await service.create(payload=payload.model_dump())
    except MembrosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Membro(**row)


@router.get("/{membro_id}", response_model=Membro)
async def get_membro(
    membro_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> Membro:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    row = await service.get(membro_id=membro_id)
    if not row:
        raise http_error(404, "Membro não encontrado.")
    return Membro(**row)


@router.patch("/{membro_id}", response_model=Membro)
async def update_membro(
    membro_id: str,
    payload: MembroUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Membro:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar membros")
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update(membro_id=membro_id, payload=data)
    except MembrosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Membro não encontrado.")
    return Membro(**row)


@router.post("/{membro_id}/status", response_model=Membro)
async def set_membro_status(
    membro_id: str,
    payload: MembroStatusUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Membro:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="alterar o status de membros")
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    try:
        row = await service.set_status(
            membro_id=membro_id, novo_status=payload.status, motivo=payload.motivo,
        )
    except MembrosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Membro não encontrado.")
    return Membro(**row)


@router.delete("/{membro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_membro(
    membro_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="remover membros")
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    ok = await service.soft_delete(membro_id=membro_id)
    if not ok:
        raise http_error(404, "Membro não encontrado.")
    return None
