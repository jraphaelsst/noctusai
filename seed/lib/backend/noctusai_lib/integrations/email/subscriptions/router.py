"""Optional FastAPI router factory: double opt-in confirm + one-click unsubscribe endpoints.

Tier ``service``: the signed token IS the credential (verified by ``AudienceService``), the same
declaration social-wiring uses for its token links. A tampered / expired / wrong-purpose token
answers **400** (the contract; never 200, never 404). The POST unsubscribe is also the RFC 8058
one-click target: mail clients POST ``List-Unsubscribe=One-Click`` (the body is ignored).

A product mounts it::

    app.include_router(make_subscription_router(get_audience_service))

and passes ``<prefix>/unsubscribe`` (default ``/api/subscriptions/unsubscribe``, on the product's
public origin) to ``AudienceService.unsubscribe_headers``.
"""
# NO `from __future__ import annotations`: FastAPI resolves Depends signatures at runtime.
from typing import Callable

from fastapi import Depends, HTTPException

from noctusai_lib.api.access_tiers import access_tier, make_router

from .service import AudienceService
from .types import InvalidSubscriptionToken

INVALID = "Link invalido ou expirado"
_TIER_REASON = "HMAC-signed double-opt-in / one-click-unsubscribe link token, verified by AudienceService"


def make_subscription_router(get_service: Callable[[], AudienceService], *, prefix: str = "/api/subscriptions"):
    router = make_router(tier="service", reason=_TIER_REASON, prefix=prefix, tags=["Subscriptions"])

    @router.get("/confirm/{token}")
    @access_tier("service", reason=_TIER_REASON)
    def confirm_info(token: str, service: AudienceService = Depends(get_service)):
        try:
            service.check_confirm_token(token)
        except InvalidSubscriptionToken:
            raise HTTPException(status_code=400, detail=INVALID)
        return {"valid": True}

    @router.post("/confirm/{token}")
    @access_tier("service", reason=_TIER_REASON)
    def confirm(token: str, service: AudienceService = Depends(get_service)):
        try:
            outcome = service.confirm(token)
        except InvalidSubscriptionToken:
            raise HTTPException(status_code=400, detail=INVALID)
        return {"ok": True, "already": outcome == "already"}

    @router.get("/unsubscribe/{token}")
    @access_tier("service", reason=_TIER_REASON)
    def unsubscribe_info(token: str, service: AudienceService = Depends(get_service)):
        try:
            service.check_unsubscribe_token(token)
        except InvalidSubscriptionToken:
            raise HTTPException(status_code=400, detail=INVALID)
        return {"valid": True}

    @router.post("/unsubscribe/{token}")
    @access_tier("service", reason=_TIER_REASON + "; RFC 8058 one-click target")
    def unsubscribe(token: str, service: AudienceService = Depends(get_service)):
        try:
            outcome = service.unsubscribe(token)
        except InvalidSubscriptionToken:
            raise HTTPException(status_code=400, detail=INVALID)
        return {"ok": True, "already": outcome == "already"}

    return router


__all__ = ["make_subscription_router"]
