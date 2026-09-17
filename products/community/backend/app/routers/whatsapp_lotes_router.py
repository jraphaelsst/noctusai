"""Lotes (sincronização) router — contract §Sincronização, items 8-13.

Auth: `Depends(get_current_user_org)` on every route. Reads allow
`admin` + `moderador` (redacted shape for `moderador`, D3); every write
(`criar`, `confirmar`, `aplicar`, `cancelar`) is `admin`-only.
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
    ConvitesPendentesResponse,
    Lote,
    LoteConfirmarRequest,
    LoteCreate,
    LoteModerador,
    mask_telefone,
)
from app.services.sincronizacao_service import SincronizacaoService, SincronizacaoServiceError
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp-lotes"])


def _service(client, org_id) -> SincronizacaoService:
    return SincronizacaoService(
        client, org_id=org_id,
        lote_max_itens=settings.lote_max_itens,
        lote_chunk=settings.lote_chunk,
        lotes_aplicados_max_dia=settings.lotes_aplicados_max_dia,
        lote_expira_horas=settings.lote_expira_horas,
    )


def _lote_out(row: dict, role: str) -> dict:
    if role == "moderador":
        itens_mascarados = [
            {**item, "telefone_mascarado": mask_telefone(item.get("telefone"))}
            for item in row.get("itens", [])
        ]
        return LoteModerador(**{**row, "itens": itens_mascarados}).model_dump()
    return Lote(**row).model_dump()


@router.post("/grupos/{grupo_id}/lotes", response_model=Lote, status_code=status.HTTP_201_CREATED)
async def criar_lote(
    grupo_id: str,
    payload: LoteCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Lote:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="gerar lotes de sincronização")
    client = get_user_client(token)
    service = _service(client, org_id)
    try:
        row = await service.criar_lote(
            grupo_id=grupo_id, acao=payload.acao,
        proposto_por=actor_uuid(user),
        )
    except SincronizacaoServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Lote(**row)


@router.get("/lotes")
async def list_lotes(
    grupo_id: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    role = get_community_role(user)
    client = get_user_client(token)
    service = _service(client, org_id)
    result = await service.list(grupo_id=grupo_id, estado=estado, page=page, page_size=page_size)
    items = [
        (LoteModerador(**{**r, "itens": []}) if role == "moderador" else Lote(**{**r, "itens": []})).model_dump()
        for r in result["items"]
    ]
    return {"items": items, "total": result["total"]}


@router.get("/lotes/{lote_id}")
async def get_lote(
    lote_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    role = get_community_role(user)
    client = get_user_client(token)
    service = _service(client, org_id)
    row = await service.get(lote_id=lote_id)
    if not row:
        raise http_error(404, "Lote não encontrado.")
    return _lote_out(row, role)


@router.post("/lotes/{lote_id}/confirmar")
async def confirmar_lote(
    lote_id: str,
    payload: LoteConfirmarRequest,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="confirmar lotes")
    client = get_user_client(token)
    service = _service(client, org_id)
    try:
        row = await service.confirmar(lote_id=lote_id, confirmado_por=actor_uuid(user))
    except SincronizacaoServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Lote(**{**row, "itens": []}).model_dump()


@router.post("/lotes/{lote_id}/aplicar")
async def aplicar_lote(
    lote_id: str,
    auth: tuple = Depends(get_current_user_org),
    waha_client=Depends(get_community_waha_client),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="aplicar lotes")
    client = get_user_client(token)
    service = _service(client, org_id)
    try:
        row = await service.aplicar(lote_id=lote_id, waha_client=waha_client)
    except SincronizacaoServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Lote(**row).model_dump()


@router.post("/lotes/{lote_id}/cancelar")
async def cancelar_lote(
    lote_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="cancelar lotes")
    client = get_user_client(token)
    service = _service(client, org_id)
    try:
        row = await service.cancelar(lote_id=lote_id)
    except SincronizacaoServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Lote(**{**row, "itens": []}).model_dump()


@router.get("/lotes/{lote_id}/convites-pendentes", response_model=ConvitesPendentesResponse)
async def convites_pendentes(
    lote_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
    waha_client=Depends(get_community_waha_client),
) -> ConvitesPendentesResponse:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="ver convites pendentes")
    client = get_user_client(token)
    service = _service(client, org_id)
    try:
        result = await service.convites_pendentes(
            lote_id=lote_id, waha_client=waha_client, page=page, page_size=page_size,
        )
    except SincronizacaoServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return ConvitesPendentesResponse(**result)
