"""Grupoterapia (group therapy sessions) router — contract §Grupoterapia,
staff side (slice BE-D).

Auth: `Depends(get_current_user_org)` on every route (401 boundary — and
403 for a `membro` JWT, per `get_current_user_org`'s own deny-by-default).
Reads allow both community roles (`admin` + `moderador`); writes are
`admin`-only via `require_admin`. The member-portal counterpart lives in
`portal_grupoterapia_router.py`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    actor_uuid,
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.grupoterapia import (
    ReservaListResponse,
    Sessao,
    SessaoCreate,
    SessaoListResponse,
    SessaoUpdate,
)
from app.services.grupoterapia_service import GrupoterapiaService, GrupoterapiaServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grupoterapia", tags=["grupoterapia"])


@router.get("/sessoes", response_model=SessaoListResponse)
async def list_sessoes(
    de: str | None = Query(default=None),
    ate: str | None = Query(default=None),
    status: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> SessaoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = GrupoterapiaService(client, org_id=org_id)
    result = await service.list(de=de, ate=ate, status=status)
    return SessaoListResponse(**result)


@router.post("/sessoes", response_model=Sessao, status_code=status.HTTP_201_CREATED)
async def create_sessao(
    payload: SessaoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Sessao:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar sessões de grupoterapia")
    client = get_user_client(token)
    service = GrupoterapiaService(client, org_id=org_id)
    body = payload.model_dump(mode="json")
    try:
        row = await service.create(payload=body)
    except GrupoterapiaServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Sessao(**row)


@router.patch("/sessoes/{sessao_id}", response_model=Sessao)
async def update_sessao(
    sessao_id: str,
    payload: SessaoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Sessao:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar sessões de grupoterapia")
    client = get_user_client(token)
    service = GrupoterapiaService(client, org_id=org_id)
    data = payload.model_dump(mode="json", exclude_none=True)
    try:
        row = await service.update(
            sessao_id=sessao_id, payload=data, autor_id=actor_uuid(user),
        )
    except GrupoterapiaServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Sessão não encontrada.")
    return Sessao(**row)


@router.delete("/sessoes/{sessao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sessao(
    sessao_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="excluir sessões de grupoterapia")
    client = get_user_client(token)
    service = GrupoterapiaService(client, org_id=org_id)
    try:
        ok = await service.delete(sessao_id=sessao_id)
    except GrupoterapiaServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not ok:
        raise http_error(404, "Sessão não encontrada.")
    return None


@router.get("/sessoes/{sessao_id}/reservas", response_model=ReservaListResponse)
async def list_reservas(
    sessao_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ReservaListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = GrupoterapiaService(client, org_id=org_id)
    result = await service.get_reservas(sessao_id=sessao_id)
    return ReservaListResponse(**result)
