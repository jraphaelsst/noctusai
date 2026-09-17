"""Flags router — contract §Ingest + flags, item 20.

Auth: `Depends(get_current_user_org)`. Both `admin` + `moderador` can
read AND resolve — "moderation IS the moderador's job" (contract).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.dependencies import actor_uuid, coerce_org_uuid, http_error, get_current_user_org, get_user_client
from app.schemas.whatsapp import Flag, FlagListResponse, FlagResolverRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp/flags", tags=["whatsapp-flags"])

_MENSAGEM_FLAGS = "mensagem_flags"


@router.get("", response_model=FlagListResponse)
async def list_flags(
    estado: str | None = Query(default=None),
    severidade: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> FlagListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    query = client.table(_MENSAGEM_FLAGS).select("*").eq("org_id", str(org_id))
    if estado:
        query = query.eq("estado", estado)
    if severidade:
        query = query.eq("severidade", severidade)
    rows = query.execute().data or []
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    return FlagListResponse(items=[Flag(**r) for r in page_rows], total=total)


@router.post("/{flag_id}/resolver", response_model=Flag)
async def resolver_flag(
    flag_id: str,
    payload: FlagResolverRequest,
    auth: tuple = Depends(get_current_user_org),
) -> Flag:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    result = (
        client.table(_MENSAGEM_FLAGS)
        .update({
            "estado": payload.estado,
            "resolvido_por": str(actor_uuid(user)) if actor_uuid(user) else None,
            "resolvido_em": datetime.now(timezone.utc).isoformat(),
        })
        .eq("org_id", str(org_id)).eq("id", str(flag_id))
        .execute()
    )
    if not result.data:
        raise http_error(404, "Sinalização não encontrada.")
    return Flag(**result.data[0])
