"""Membros router — contract §Membros.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
Reads allow both community roles — no extra gate. Writes are
`admin`-only via `require_admin`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    actor_uuid,
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_core_client,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.membros import (
    AcessoOut,
    Evento,
    EventoCreate,
    EventoListResponse,
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
        row = await service.update(membro_id=membro_id, payload=data, autor_id=actor_uuid(user))
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
            autor_id=actor_uuid(user),
        )
    except MembrosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Membro não encontrado.")
    return Membro(**row)


@router.post("/{membro_id}/acesso", response_model=AcessoOut, status_code=status.HTTP_201_CREATED)
async def criar_acesso_membro(
    membro_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> AcessoOut:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar acesso de membros")
    client = get_user_client(token)
    core_client = get_core_client()
    service = MembrosService(client, org_id=org_id)
    try:
        result = await service.criar_acesso(
            membro_id=membro_id, core_client=core_client, autor_id=actor_uuid(user),
        )
    except MembrosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if result is None:
        raise http_error(404, "Membro não encontrado.")
    return AcessoOut(**result)


@router.get("/{membro_id}/eventos", response_model=EventoListResponse)
async def list_membro_eventos(
    membro_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> EventoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    core_client = get_core_client()
    service = MembrosService(client, org_id=org_id)
    result = await service.list_eventos(
        membro_id=membro_id, page=page, page_size=page_size, core_client=core_client,
    )
    return EventoListResponse(**result)


@router.post("/{membro_id}/eventos", response_model=Evento, status_code=status.HTTP_201_CREATED)
async def criar_membro_evento(
    membro_id: str,
    payload: EventoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Evento:
    # Staff, moderador allowed (contract §Identity) — no `require_admin` gate.
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = MembrosService(client, org_id=org_id)
    autor_nome = (getattr(user, "user_metadata", None) or {}).get("nome")
    row = await service.criar_evento(
        membro_id=membro_id, tipo=payload.tipo, descricao=payload.descricao,
        autor_id=actor_uuid(user), autor_nome=autor_nome,
    )
    if row is None:
        raise http_error(404, "Membro não encontrado.")
    return Evento(**row)


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
