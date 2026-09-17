"""Grupos + sessão router — contract §Grupos, items 1-7.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
Reads allow `admin` + `moderador`; writes are `admin`-only.
`GET /{id}/convite` and `POST /{id}/convite/revogar` are **admin only**
(403 for `moderador`, never an omitted-field redaction — the whole
endpoint is inaccessible). Roster reads (embedded in `GET /{id}`) mask
phones + omit the raw JID for `moderador` (D3).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_community_waha_client,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.whatsapp import (
    ConviteOut,
    Grupo,
    GrupoCreate,
    GrupoListResponse,
    GrupoRosterItem,
    GrupoRosterItemModerador,
    GrupoUpdate,
    SessaoOut,
    SincronizarRosterResponse,
    mask_telefone,
)
from noctusai_lib.integrations.whatsapp.types import WhatsAppGroupClient

from app.services.grupos_service import GruposService, GruposServiceError
from app.services.grupos_service import get_sessao as get_sessao_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp-grupos"])


def _roster_for_role(rows: list[dict], role: str) -> list[dict]:
    if role == "moderador":
        return [
            GrupoRosterItemModerador(
                **{**row, "telefone_mascarado": mask_telefone(row.get("telefone"))},
            ).model_dump()
            for row in rows
        ]
    return [GrupoRosterItem(**row).model_dump() for row in rows]


@router.get("/grupos", response_model=GrupoListResponse)
async def list_grupos(
    ativo: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> GrupoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    result = await service.list(ativo=ativo, page=page, page_size=page_size)
    return GrupoListResponse(items=[Grupo(**r) for r in result["items"]], total=result["total"])


@router.post("/grupos", response_model=Grupo, status_code=status.HTTP_201_CREATED)
async def create_grupo(
    payload: GrupoCreate,
    auth: tuple = Depends(get_current_user_org),
    waha_client: WhatsAppGroupClient = Depends(get_community_waha_client),
) -> Grupo:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="cadastrar grupos")
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    try:
        row = await service.create(payload=payload.model_dump(), waha_client=waha_client)
    except GruposServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Grupo(**row)


@router.get("/grupos/{grupo_id}")
async def get_grupo(
    grupo_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    role = get_community_role(user)
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    row = await service.get(grupo_id=grupo_id)
    if not row:
        raise http_error(404, "Grupo não encontrado.")
    roster_rows = await service.get_roster(grupo_id=grupo_id)
    body = Grupo(**row).model_dump()
    body["membros"] = _roster_for_role(roster_rows, role)
    return body


@router.patch("/grupos/{grupo_id}", response_model=Grupo)
async def update_grupo(
    grupo_id: str,
    payload: GrupoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Grupo:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar grupos")
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    row = await service.update(grupo_id=grupo_id, payload=data)
    if not row:
        raise http_error(404, "Grupo não encontrado.")
    return Grupo(**row)


@router.post("/grupos/{grupo_id}/sincronizar-roster", response_model=SincronizarRosterResponse)
async def sincronizar_roster(
    grupo_id: str,
    auth: tuple = Depends(get_current_user_org),
    waha_client: WhatsAppGroupClient = Depends(get_community_waha_client),
) -> SincronizarRosterResponse:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="sincronizar o roster de grupos")
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    try:
        count = await service.sincronizar_roster(grupo_id=grupo_id, waha_client=waha_client)
    except GruposServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return SincronizarRosterResponse(participantes=count)


@router.get("/grupos/{grupo_id}/convite", response_model=ConviteOut)
async def get_convite(
    grupo_id: str,
    auth: tuple = Depends(get_current_user_org),
    waha_client: WhatsAppGroupClient = Depends(get_community_waha_client),
) -> ConviteOut:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="ver o link de convite")
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    try:
        link = await service.get_convite(grupo_id=grupo_id, waha_client=waha_client)
    except GruposServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return ConviteOut(link=link)


@router.post("/grupos/{grupo_id}/convite/revogar", response_model=ConviteOut)
async def revogar_convite(
    grupo_id: str,
    auth: tuple = Depends(get_current_user_org),
    waha_client: WhatsAppGroupClient = Depends(get_community_waha_client),
) -> ConviteOut:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="revogar o link de convite")
    client = get_user_client(token)
    service = GruposService(client, org_id=org_id)
    try:
        link = await service.revogar_convite(grupo_id=grupo_id, waha_client=waha_client)
    except GruposServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return ConviteOut(link=link)


@router.get("/sessao", response_model=SessaoOut)
async def get_sessao_endpoint(
    auth: tuple = Depends(get_current_user_org),
    waha_client: WhatsAppGroupClient = Depends(get_community_waha_client),
) -> SessaoOut:
    _user, _token, _raw_org = auth
    try:
        info = await get_sessao_info(waha_client=waha_client)
    except GruposServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return SessaoOut(**info)
