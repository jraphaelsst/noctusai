"""WhatsApp inbound webhook — contract §3 item 19.

Mounts the SEED router (`create_whatsapp_webhook_router`) verbatim at
the STATIC path `/api/webhooks/whatsapp` — no second WAHA webhook
verifier, no second dedup. `on_message` is
`app.services.ingest_service.handle_inbound`. Kept working unchanged
(Slice C, user decision 2026-09-17) — this is community's WAHA session
today, regardless of the connections mechanism below.

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

**`POST /api/whatsapp/webhook/{token}`** (below, distinct prefix —
`/api/whatsapp/webhook`, singular, vs. the static mount's
`/api/webhooks/whatsapp`) is the per-connection inbound endpoint the
`whatsapp_connections_router` mints a `webhook_url` for on
`create_connection`. Resolves the line via its opaque
`webhook_token` (`resolve_by_webhook_token`) and hands off to the SAME
`handle_inbound` — no second ingest pipeline. Fail-closed HMAC, same
posture as the static route (`settings.community_waha_webhook_hmac_
secret`, unset ⇒ bypass — early-dev only, exactly as `create_whatsapp_
webhook_router` behaves above). `NOC-REMEDIATE[community-waha-pairing]`:
no number is paired yet (see `products/community/README.md`).
"""
# No `from __future__ import annotations`: slowapi's @limiter.limit inspects
# the endpoint signature at runtime and breaks on PEP 563 string annotations
# (repo check check_slowapi_with_pep563).

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from noctusai_lib.integrations.whatsapp import (
    WhatsAppIgnoredEvent,
    WhatsAppPayloadError,
    build_whatsapp_connection_store,
    get_webhook_dedup,
    parse_waha_inbound_message,
    resolve_by_webhook_token,
)
from noctusai_lib.security.api_keys import EncryptionNotConfigured
from noctusai_lib.security.webhook_signatures import verify_hmac_sha256_hex

from app.config import settings
from app.dependencies import get_admin_client
from app.rate_limit import limiter
from app.services.ingest_service import handle_inbound

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp-webhook"])


@limiter.limit(settings.webhook_rate_limit)
async def _rate_limit_whatsapp_webhook(request: Request) -> None:
    return None


def _build_redis_client():
    if not getattr(settings, "redis_url", None):
        return None
    import redis as _redis

    return _redis.from_url(settings.redis_url)


def _build_inner_router() -> APIRouter:
    from noctusai_lib.integrations.whatsapp import (
        WhatsAppSettings,
        create_whatsapp_webhook_router,
    )

    whatsapp_settings = WhatsAppSettings(
        base_url=settings.community_waha_base_url or "http://unset.invalid",
        api_key=settings.community_waha_api_key or None,
        session=settings.community_waha_session,
        external_base_url=settings.community_waha_external_base_url or None,
        webhook_hmac_secret=settings.community_waha_webhook_hmac_secret or None,
    )

    dedup = get_webhook_dedup(redis_client=_build_redis_client())

    return create_whatsapp_webhook_router(
        settings=whatsapp_settings, on_message=handle_inbound, dedup=dedup,
    )


router.include_router(
    _build_inner_router(),
    prefix="/api/webhooks/whatsapp",
    dependencies=[Depends(_rate_limit_whatsapp_webhook)],
)


# ─── per-connection token webhook — `whatsapp_connections_router.py` ──────

def _token_webhook_store_dep():
    """Returns `None` (never raises) when `ENCRYPTION_KEY` is unusable —
    the route below maps that to a 404 rather than leaking config state
    to an unauthenticated caller, same posture as `_store_dep`'s
    `EncryptionNotConfigured` -> 503 elsewhere, deliberately relaxed here
    because a webhook endpoint's 503 vs 404 distinction is not something
    an external WAHA server can act on either way."""
    try:
        return build_whatsapp_connection_store(
            get_admin_client(), encryption_key=settings.encryption_key, schema="community",
        )
    except EncryptionNotConfigured:
        return None


# Separate dedup instance from the static route's (module-scoped, built
# once) — same WAHA subscribes `message` + `message.any` duplicate-delivery
# shape, same Redis-backed-when-configured / in-memory-otherwise fallback.
_token_webhook_dedup = get_webhook_dedup(redis_client=_build_redis_client())


@router.post("/api/whatsapp/webhook/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def whatsapp_webhook_by_token(
    token: str,
    request: Request,
    x_webhook_hmac_sha256: str | None = Header(default=None, alias="X-Webhook-Hmac-SHA256"),
    store=Depends(_token_webhook_store_dep),
) -> Response:
    """Per-connection token-scoped WAHA webhook endpoint.

    Resolves the connection via the opaque `token` path parameter.
    Unknown token -> 404 (generic, no token enumeration — never logs the
    token value). Delegates to the SAME `handle_inbound` the static
    `/api/webhooks/whatsapp` mount uses — no second ingest pipeline.
    """
    body = await request.body()

    if settings.community_waha_webhook_hmac_secret:
        if not x_webhook_hmac_sha256 or not verify_hmac_sha256_hex(
            body,
            signature_hex=x_webhook_hmac_sha256,
            secret=settings.community_waha_webhook_hmac_secret,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    if store is None:
        logger.warning(
            "whatsapp_webhook_by_token: encryption not configured, cannot resolve token"
        )
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    connection = resolve_by_webhook_token(store, token)
    if connection is None:
        logger.debug("whatsapp_webhook_by_token: unknown token (404)")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    logger.debug(
        "whatsapp_webhook_by_token: resolved connection id=%s session=%s",
        connection.id, connection.session_name,
    )

    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=status.HTTP_200_OK)

    try:
        inbound = parse_waha_inbound_message(payload)
    except WhatsAppIgnoredEvent as exc:
        logger.debug("whatsapp_webhook_by_token: ignored (%s)", exc)
        return Response(status_code=status.HTTP_200_OK)
    except WhatsAppPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if inbound.provider_message_id and not _token_webhook_dedup.claim(inbound.provider_message_id):
        logger.debug("whatsapp_webhook_by_token: dedup hit")
        return Response(status_code=status.HTTP_200_OK)

    await handle_inbound(inbound)
    return Response(status_code=status.HTTP_200_OK)
