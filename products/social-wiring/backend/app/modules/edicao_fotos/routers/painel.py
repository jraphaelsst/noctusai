"""`GET /api/edicao-fotos/painel` — contract §8.

"Scope follows `capacidades.dashboard`" (contract §2/§8): platform admins
see everything, with an optional `org_id` filter down to one org;
agency admins ALWAYS see their own org, regardless of any `org_id` they
pass (never trust a client-supplied org boundary for a non-platform-admin
caller); corretores get 403 (they are not in the role matrix's "Platform
dashboard" / "Org dashboard" rows at all — `require_org_admin` is exactly
that gate, already shared with `PUT /configuracoes`)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from noctusai_lib.domain.photo_editing import Actor

from app.modules.edicao_fotos.deps import get_painel_client, require_org_admin
from app.modules.edicao_fotos.services import painel as painel_service

router = APIRouter(prefix="/api/edicao-fotos/painel", tags=["edicao-fotos"])


@router.get("")
async def painel_route(
    actor: Actor = Depends(require_org_admin),
    client: Any = Depends(get_painel_client),
    desde: Optional[date] = Query(default=None),
    ate: Optional[date] = Query(default=None),
    org_id: Optional[str] = Query(
        default=None, description="Platform admin only — filter to one org; ignored for agency admins."
    ),
) -> dict:
    filtro_org = org_id if actor.is_platform_admin else actor.org_id
    return painel_service.painel(client, org_id=filtro_org, desde=desde, ate=ate)


__all__ = ["router"]
