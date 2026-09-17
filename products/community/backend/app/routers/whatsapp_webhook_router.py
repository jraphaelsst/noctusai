"""WhatsApp inbound webhook — contract §3 item 19.

Mounts the SEED router (`create_whatsapp_webhook_router`) verbatim — no
second WAHA webhook verifier, no second dedup. `on_message` is
`app.services.ingest_service.handle_inbound`.

**Rate limiting the mounted seed router without touching seed code.**
`create_whatsapp_webhook_router`'s internal route function has no
`@limiter.limit(...)` decorator (the factory is generic — it doesn't
know this product's `Limiter` instance). slowapi's `@limiter.limit(...)`
decorates any async callable with a `request: Request` parameter — not
necessarily the path-operation function itself — so a tiny dependency
decorated with it, passed via `include_router(..., dependencies=[...])`,
rate-limits every route in the included router without forking it.
`headers_enabled` is off (this product's `create_limiter()` default),
so the decorator's response-header injection path is a no-op regardless
of what the wrapped dependency returns.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.rate_limit import limiter
from app.services.ingest_service import handle_inbound

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp-webhook"])


@limiter.limit(settings.webhook_rate_limit)
async def _rate_limit_whatsapp_webhook(request: Request) -> None:
    return None


def _build_inner_router() -> APIRouter:
    from noctusai_lib.integrations.whatsapp import (
        WhatsAppSettings,
        create_whatsapp_webhook_router,
        get_webhook_dedup,
    )

    whatsapp_settings = WhatsAppSettings(
        base_url=settings.community_waha_base_url or "http://unset.invalid",
        api_key=settings.community_waha_api_key or None,
        session=settings.community_waha_session,
        external_base_url=settings.community_waha_external_base_url or None,
        webhook_hmac_secret=settings.community_waha_webhook_hmac_secret or None,
    )

    redis_client = None
    if getattr(settings, "redis_url", None):
        import redis as _redis

        redis_client = _redis.from_url(settings.redis_url)

    dedup = get_webhook_dedup(redis_client=redis_client)

    return create_whatsapp_webhook_router(
        settings=whatsapp_settings, on_message=handle_inbound, dedup=dedup,
    )


router.include_router(
    _build_inner_router(),
    prefix="/api/webhooks/whatsapp",
    dependencies=[Depends(_rate_limit_whatsapp_webhook)],
)
