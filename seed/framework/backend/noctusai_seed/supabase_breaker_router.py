"""``/api/platform/supabase-breaker`` — platform-admin surface of the Supabase request breaker.

Auto-mounted on EVERY product by ``create_product_app`` (registry key ``"supabase_breaker"``), like ``me`` / ``mfa``:

* ``GET  /api/platform/supabase-breaker``        — this process's breaker state (held sources, fleet key, counts).
* ``POST /api/platform/supabase-breaker/rearm``  — release a held source (or ``fleet``); a reason is REQUIRED.
* ``POST /api/platform/supabase-breaker/trip``   — hold a background source by hand (never ``http``).

Tier ``platform`` (strict: no token 401, anyone but a ``noctus_users.role='admin'`` 403). The role read goes through the
trusted ``resolve_platform_admin_role``; it needs core Supabase, so when Supabase itself is the thing that is down use the
independent path ``noctus.dev.supabase_breaker`` (talks to Redis over the VPS, no Supabase).

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.api.access_tiers import access_tier, make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.schemas import StrictHttpModel
from noctusai_lib.primitives.supabase_breaker import HTTP_SOURCE, get_breaker

logger = logging.getLogger(__name__)

__all__ = ["create_supabase_breaker_router"]

_TIER_REASON = "platform-admin only: noctus_users.role == 'admin' via resolve_platform_admin_role"


class RearmBody(StrictHttpModel):
    source: str
    reason: str


class TripBody(StrictHttpModel):
    source: str
    reason: str


def create_supabase_breaker_router(deps) -> APIRouter:
    async def platform_admin_dep(auth=Depends(deps.get_current_user)) -> Any:
        user, _token = auth
        role = await run_blocking(resolve_platform_admin_role, deps.get_core_client(), user.id)
        if role != "admin":
            raise HTTPException(
                status_code=403,
                detail={"detail": "Restrito a administradores da plataforma NoctusAI", "code": "platform_admin_required"},
            )
        return user

    router = make_router(tier="platform", guard=platform_admin_dep, prefix="/api/platform/supabase-breaker",
                         tags=["Platform · Supabase breaker"])

    def _actor(user: Any) -> str:
        return str(getattr(user, "email", None) or getattr(user, "id", "unknown"))

    @router.get("")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_status() -> dict:
        breaker = get_breaker()
        await run_blocking(breaker.refresh)
        return breaker.status()

    @router.post("/rearm")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_rearm(body: RearmBody, user=Depends(platform_admin_dep)) -> dict:
        if not body.reason.strip():
            raise HTTPException(status_code=422, detail={"detail": "reason is required", "code": "reason_required"})
        try:
            return await run_blocking(get_breaker().rearm, body.source, by=_actor(user), reason=body.reason.strip())
        except Exception as exc:  # the key may still exist: say so, never pretend it was released
            logger.error("breaker rearm failed for %s", body.source, exc_info=True)
            raise HTTPException(status_code=502, detail={"detail": f"re-arm failed: {type(exc).__name__}: {exc}",
                                                         "code": "rearm_failed"})

    @router.post("/trip")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_trip(body: TripBody, user=Depends(platform_admin_dep)) -> dict:
        if body.source == HTTP_SOURCE or not body.source.strip():
            raise HTTPException(status_code=422, detail={"detail": "only background sources can be tripped",
                                                         "code": "source_invalid"})
        if not body.reason.strip():
            raise HTTPException(status_code=422, detail={"detail": "reason is required", "code": "reason_required"})
        created = await run_blocking(get_breaker().trip, body.source, reason=body.reason.strip(), by=_actor(user))
        return {"ok": True, "source": body.source, "created": created}

    return router
