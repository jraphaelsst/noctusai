"""Pagamentos router — contract §Manager+member views, amendment A16/P3.

`GET /api/pagamentos` is `admin`-only — a `moderador` gets a strict 403
BEFORE the service ever runs (P3: "moderador sees subscription state
only"; `pix_payload`/`url_fatura`/`cobranca_externa_id` never reach a
moderador on any route). Reuses `require_admin` (401 boundary via
`Depends(get_current_user_org)` first, then the role gate) — the SAME
403 shape module 1's write endpoints already use, just applied to a
READ here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    coerce_org_uuid,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.pagamentos import Pagamento
from app.services.pagamentos_service import PagamentosService

router = APIRouter(prefix="/api/pagamentos", tags=["pagamentos"])


@router.get("")
async def list_pagamentos(
    membro_id: str | None = Query(default=None),
    assinatura_id: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="ver pagamentos")
    client = get_user_client(token)
    service = PagamentosService(client, org_id=org_id)
    result = await service.list(
        membro_id=membro_id, assinatura_id=assinatura_id, estado=estado,
        page=page, page_size=page_size,
    )
    items = [Pagamento(**item).model_dump() for item in result["items"]]
    return {"items": items, "total": result["total"]}
