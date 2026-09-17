"""Assinaturas router — contract §Manager+member views, amendment P3.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
`GET` allows both community roles, but `moderador` gets the REDACTED
`AssinaturaModerador` shape (amendment P3 — an exhaustive allow-list,
not a partial mask); `admin` gets the full `Assinatura` shape. The
response is built as a plain dict (no `response_model=` on the list
route) precisely so the two shapes can coexist behind one endpoint.
`POST /{id}/cancelar` is `admin`-only.
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
from app.schemas.assinaturas import Assinatura, AssinaturaCancelRequest, AssinaturaModerador
from app.services.assinaturas_service import AssinaturasService, AssinaturasServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assinaturas", tags=["assinaturas"])


@router.get("")
async def list_assinaturas(
    membro_id: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    role = get_community_role(user)
    client = get_user_client(token)
    service = AssinaturasService(client, org_id=org_id)
    result = await service.list(
        membro_id=membro_id, estado=estado, page=page, page_size=page_size,
    )
    if role == "moderador":
        items = [AssinaturaModerador(**item).model_dump() for item in result["items"]]
    else:
        items = [Assinatura(**item).model_dump() for item in result["items"]]
    return {"items": items, "total": result["total"]}


@router.post("/{assinatura_id}/cancelar", response_model=Assinatura)
async def cancelar_assinatura(
    assinatura_id: str,
    payload: AssinaturaCancelRequest,
    auth: tuple = Depends(get_current_user_org),
) -> Assinatura:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="cancelar assinaturas")
    client = get_user_client(token)
    service = AssinaturasService(client, org_id=org_id)
    try:
        row = await service.cancelar(assinatura_id=assinatura_id, motivo=payload.motivo)
    except AssinaturasServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Assinatura(**row)
