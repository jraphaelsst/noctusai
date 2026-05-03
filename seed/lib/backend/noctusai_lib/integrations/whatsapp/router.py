"""FastAPI factory for the WhatsApp inbound webhook.

Mount via `standard_routers=[..., "whatsapp_webhook"]` in
`create_product_app(...)`, OR include directly:

    from noctusai_lib.integrations.whatsapp import (
        create_whatsapp_webhook_router, WhatsAppSettings,
    )

    app.include_router(
        create_whatsapp_webhook_router(
            settings=whatsapp_settings,
            on_message=handle_inbound,  # consumer-supplied callable
        ),
        prefix="/webhooks/whatsapp",
    )

The consumer's `on_message(inbound: WhatsAppInboundMessage) -> None`
callable owns persistence + dispatch — the router only handles
HTTP plumbing + signature verification + idempotency.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Set

from fastapi import APIRouter, Header, HTTPException, Request, status

from noctusai_lib.integrations.whatsapp.mappers import parse_waha_inbound_message
from noctusai_lib.integrations.whatsapp.settings import WhatsAppSettings
from noctusai_lib.integrations.whatsapp.types import (
    WhatsAppIgnoredEvent,
    WhatsAppInboundMessage,
    WhatsAppPayloadError,
)
from noctusai_lib.security.webhook_signatures import verify_hmac_sha256_hex

logger = logging.getLogger(__name__)

InboundHandler = Callable[[WhatsAppInboundMessage], Awaitable[None]]


def create_whatsapp_webhook_router(
    settings: WhatsAppSettings,
    on_message: InboundHandler,
    *,
    signature_header: str = "X-Webhook-Hmac-SHA256",
) -> APIRouter:
    """Build a FastAPI APIRouter that accepts WAHA inbound webhooks.

    Behavior:
    - Verifies HMAC-SHA256 hex signature when
      `settings.webhook_hmac_secret` is set; rejects with 401 on mismatch.
    - Idempotency: in-process set of seen `provider_message_id` values.
      Reorder-safe across worker restart only when consumers wire their
      own DB-backed dedup; this layer's set is best-effort within a
      single process. (Sibling stored seen IDs in Redis ZSET; that's
      Phase 3 chatbot-framework scope, not router scope.)
    - Calls `on_message(inbound)` exactly once per fresh
      `provider_message_id`.
    - Returns 200 on success, 200 on ignored events (per WAHA's
      tolerance for non-2xx → retry semantics; ignored events should
      not trigger retries).
    """
    router = APIRouter()
    seen_ids: Set[str] = set()

    @router.post("")
    async def waha_inbound(
        request: Request,
        x_webhook_hmac_sha256: str | None = Header(default=None, alias=signature_header),
    ) -> dict[str, str]:
        body = await request.body()

        if settings.webhook_hmac_secret:
            if not x_webhook_hmac_sha256:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing webhook signature header",
                )
            if not verify_hmac_sha256_hex(
                body,
                signature_hex=x_webhook_hmac_sha256,
                secret=settings.webhook_hmac_secret,
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON",
            ) from exc

        try:
            inbound = parse_waha_inbound_message(payload)
        except WhatsAppIgnoredEvent as exc:
            logger.debug("WhatsApp inbound ignored: %s", exc)
            return {"status": "ignored"}
        except WhatsAppPayloadError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if inbound.provider_message_id and inbound.provider_message_id in seen_ids:
            logger.debug(
                "WhatsApp inbound dedup hit: %s", inbound.provider_message_id
            )
            return {"status": "duplicate"}

        if inbound.provider_message_id:
            seen_ids.add(inbound.provider_message_id)

        await on_message(inbound)
        return {"status": "accepted"}

    return router
