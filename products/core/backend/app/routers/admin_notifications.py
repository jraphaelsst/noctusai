"""Notificações — platform-admin surface over every owner-facing notification the products send.

  GET   /api/admin/notifications                    → catalog grouped by product, switch state, 30-day send stats
  GET   /api/admin/notifications/sends              → recent dispatch ledger (?product=&kind=&limit=)
  PATCH /api/admin/notifications/{product}          → {enabled} for every kind of the product
  PATCH /api/admin/notifications/{product}/{kind}   → {enabled} for one kind

Access: platform tier — `require_platform_admin_dep` on the router AND on every route (401 without a valid bearer,
403 for a non-admin). Code only, no vendor call. Products read the switch through the seed gate with a 60 s cache.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException, Path, Query
from pydantic import BaseModel

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.primitives.timeutil import now_utc

from app.services import notification_catalog_service as svc
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

router = make_router(
    tier="platform", guard=require_platform_admin_dep,
    prefix="/api/admin/notifications", tags=["Admin · Notificações"],
)

_SLUG = r"^[a-z0-9][a-z0-9-]{0,99}$"
_KIND = r"^[a-z0-9_]{1,80}$"


class SwitchBody(BaseModel):
    enabled: bool


def _user_id(auth: AuthContext) -> Optional[str]:
    uid = getattr(auth, "user_id", None) or getattr(getattr(auth, "user", None), "id", None)
    return str(uid) if uid else None


@router.get("")
async def get_catalog(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return {"data": await run_blocking(svc.list_catalog, db, now_utc())}


@router.get("/sends")
async def get_sends(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    product: Optional[str] = Query(None, pattern=_SLUG),
    kind: Optional[str] = Query(None, pattern=_KIND),
    limit: int = Query(50, ge=1, le=500),
):
    rows = await run_blocking(lambda: svc.list_sends(db, product=product, kind=kind, limit=limit))
    return {"data": rows}


async def _switch(db: Any, auth: AuthContext, product: str, kind: Optional[str], enabled: bool) -> dict:
    try:
        changed = await run_blocking(
            lambda: svc.set_enabled(db, product=product, kind=kind, enabled=enabled, user_id=_user_id(auth),
                                    now=now_utc())
        )
    except svc.KindNotFound:
        raise HTTPException(status_code=404, detail={"code": "notificacao_nao_encontrada",
                                                     "message": "Notificação não encontrada no catálogo."})
    return {"data": {"product": product, "kind": kind, "enabled": enabled, "changed": changed}}


@router.patch("/{product}")
async def switch_product(
    body: SwitchBody,
    product: str = Path(..., pattern=_SLUG),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return await _switch(db, auth, product, None, body.enabled)


@router.patch("/{product}/{kind}")
async def switch_kind(
    body: SwitchBody,
    product: str = Path(..., pattern=_SLUG),
    kind: str = Path(..., pattern=_KIND),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return await _switch(db, auth, product, kind, body.enabled)
