"""Transmissões router — contract §Transmissões, items 14-18.

Auth: `Depends(get_current_user_org)` on every route. Reads allow
`admin` + `moderador`; every write is `admin`-only.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    actor_uuid,
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_community_waha_client,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.whatsapp import (
    Transmissao,
    TransmissaoCreate,
    TransmissaoEnviarResponse,
    TransmissaoListResponse,
    TransmissaoUpdate,
)
from app.services.transmissoes_service import TransmissoesService, TransmissoesServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp/transmissoes", tags=["whatsapp-transmissoes"])


@router.get("", response_model=TransmissaoListResponse)
async def list_transmissoes(
    estado: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> TransmissaoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = TransmissoesService(client, org_id=org_id)
    result = await service.list(estado=estado, page=page, page_size=page_size)
    return TransmissaoListResponse(**result)


@router.post("", response_model=Transmissao, status_code=status.HTTP_201_CREATED)
async def create_transmissao(
    payload: TransmissaoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Transmissao:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="criar transmissões")
    client = get_user_client(token)
    service = TransmissoesService(client, org_id=org_id)
    try:
        row = await service.create(payload=payload.model_dump(), criada_por=actor_uuid(user))
    except TransmissoesServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Transmissao(**row)


@router.patch("/{transmissao_id}", response_model=Transmissao)
async def update_transmissao(
    transmissao_id: str,
    payload: TransmissaoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Transmissao:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar transmissões")
    client = get_user_client(token)
    service = TransmissoesService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update(transmissao_id=transmissao_id, payload=data)
    except TransmissoesServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Transmissão não encontrada.")
    return Transmissao(**row)


@router.post("/{transmissao_id}/enviar", response_model=TransmissaoEnviarResponse, status_code=status.HTTP_202_ACCEPTED)
async def enviar_transmissao(
    transmissao_id: str,
    auth: tuple = Depends(get_current_user_org),
    waha_client=Depends(get_community_waha_client),
) -> TransmissaoEnviarResponse:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="enviar transmissões")
    client = get_user_client(token)
    service = TransmissoesService(client, org_id=org_id)
    try:
        result = await service.enviar(transmissao_id=transmissao_id, waha_client=waha_client)
    except TransmissoesServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return TransmissaoEnviarResponse(**result)


@router.delete("/{transmissao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transmissao(
    transmissao_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="excluir transmissões")
    client = get_user_client(token)
    service = TransmissoesService(client, org_id=org_id)
    try:
        ok = await service.delete(transmissao_id=transmissao_id)
    except TransmissoesServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not ok:
        raise http_error(404, "Transmissão não encontrada.")
    return None
