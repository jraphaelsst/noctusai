"""``/api/platform/supabase-breaker`` — platform-admin surface of the Supabase request breaker.

Auto-mounted on EVERY product by ``create_product_app`` (registry key ``"supabase_breaker"``), like ``me`` / ``mfa``:

* ``GET  /api/platform/supabase-breaker``        — this process's breaker state (held sources, fleet key, counts).
* ``POST /api/platform/supabase-breaker/rearm``  — release a held background source; a reason is REQUIRED.
* ``POST /api/platform/supabase-breaker/trip``   — hold a background source by hand.

``fleet`` and ``http`` are NOT accepted anywhere here (the fleet kill switch is ops-only: ``noctus.dev.supabase_breaker``;
``http`` is never held). Auth is the canonical ``require_platform_admin`` (strict 401 / 403, the admin-MFA AAL2 assurance
gate included): a session-cookie-only ``get_auth_context`` (``NoApiTokensResolver``: a ``noc_``/``pk_`` bearer is a strict 401 — a standard router cannot know each product's token storage) + the trusted ``noctus_users.role`` read. That read
needs core Supabase, so when Supabase itself is the thing that is down use the independent MCP tool.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from noctusai_lib.api.access_tiers import access_tier, make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.platform import require_platform_admin
from noctusai_lib.api.auth.session import NoApiTokensResolver, make_get_auth_context
from noctusai_lib.api.schemas import StrictHttpModel
from noctusai_lib.primitives.supabase_breaker import BREAKER_REASON_RE, BREAKER_SOURCE_RE, get_breaker

logger = logging.getLogger(__name__)

__all__ = ["create_supabase_breaker_router"]

_TIER_REASON = "platform-admin only: require_platform_admin (noctus_users.role == 'admin' + admin-MFA assurance)"
_SESSION_COOKIE = "nai_session"


_REASON_PATTERN = BREAKER_REASON_RE.pattern  # printable only: no control characters


class RearmBody(StrictHttpModel):
    source: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=300, pattern=_REASON_PATTERN)


class TripBody(StrictHttpModel):
    source: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=300, pattern=_REASON_PATTERN)


def _source_or_422(source: str) -> str:
    if not BREAKER_SOURCE_RE.match(source):
        raise HTTPException(
            status_code=422,
            detail={"detail": "source must be a background source (worker:<types> | scheduler:<job> | gate:<name> | "
                              "unattributed); the fleet key is ops-only", "code": "source_invalid"},
        )
    return source


def create_supabase_breaker_router(deps, settings) -> APIRouter:
    from noctusai_seed.auth_router import get_session_store  # deferred: auth_router is heavy

    get_auth_context = make_get_auth_context(
        session_store=get_session_store(settings),
        api_token_resolver=NoApiTokensResolver(),  # declared policy: session cookie only, no machine tokens
        session_cookie_name=_SESSION_COOKIE,
    )
    platform_admin = require_platform_admin(get_auth_context=get_auth_context, get_core_client=deps.get_core_client)
    router = make_router(tier="platform", guard=platform_admin, prefix="/api/platform/supabase-breaker",
                         tags=["Platform · Supabase breaker"])

    def _actor(ctx: Any) -> str:
        return str(getattr(ctx, "user_id", None) or "unknown")

    @router.get("")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_status() -> dict:
        breaker = get_breaker()
        await run_blocking(breaker.refresh)
        return breaker.status()

    @router.post("/rearm")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_rearm(body: RearmBody, ctx=Depends(platform_admin)) -> dict:
        source = _source_or_422(body.source)
        if not body.reason.strip():
            raise HTTPException(status_code=422, detail={"detail": "reason is required", "code": "reason_required"})
        try:
            return await run_blocking(get_breaker().rearm, source, by=_actor(ctx), reason=body.reason.strip())
        except Exception as exc:  # the key may still exist: say so, never pretend it was released
            logger.error("breaker rearm failed for %s", source, exc_info=True)
            raise HTTPException(status_code=502, detail={"detail": f"re-arm failed: {type(exc).__name__}",
                                                         "code": "rearm_failed"})

    @router.post("/trip")
    @access_tier("platform", reason=_TIER_REASON)
    async def breaker_trip(body: TripBody, ctx=Depends(platform_admin)) -> dict:
        source = _source_or_422(body.source)
        if not body.reason.strip():
            raise HTTPException(status_code=422, detail={"detail": "reason is required", "code": "reason_required"})
        created = await run_blocking(get_breaker().trip, source, reason=body.reason.strip(), by=_actor(ctx))
        return {"ok": True, "source": source, "created": created}

    return router
