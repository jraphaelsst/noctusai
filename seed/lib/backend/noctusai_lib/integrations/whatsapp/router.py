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
from typing import Awaitable, Callable

from fastapi import APIRouter, Header, HTTPException, Request, status

from noctusai_lib.integrations.whatsapp.dedup import (
    InMemoryWebhookDedup,
    WebhookDedup,
)
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
    dedup: WebhookDedup | None = None,
) -> APIRouter:
    """Build a FastAPI APIRouter that accepts WAHA inbound webhooks.

    Behavior:
    - Verifies HMAC-SHA256 hex signature when
      `settings.webhook_hmac_secret` is set; rejects with 401 on mismatch.
    - **Persistent dedup pre-filter** (SESSION-NOTES §4.1): WAHA
      subscribes the webhook to BOTH ``message`` AND ``message.any``,
      so the same ``provider_message_id`` arrives twice within
      milliseconds. The `dedup` seam's `claim(...)` is checked right
      after parse (and before `on_message`) so the duplicate returns
      200 in ~25ms without invoking the consumer / OpenAI. Inject a
      `RedisWebhookDedup` (via `get_webhook_dedup(redis_client=...)`)
      for cross-process restart-tolerant dedup; the DB
      ``UNIQUE(provider_message_id)`` backstop (chatbot
      ``message_store`` seam, Engineer CHATBOT) is the consumer's
      restart-survival layer composed inside `on_message`. When no
      `dedup` is supplied this layer falls back to a process-local
      `InMemoryWebhookDedup` (best-effort within one process — same
      guarantee the prior in-process `set()` gave, now via the seam).
    - Calls `on_message(inbound)` exactly once per fresh
      `provider_message_id`.
    - Returns 200 on success, 200 on ignored events (per WAHA's
      tolerance for non-2xx → retry semantics; ignored events should
      not trigger retries).
    """
    router = APIRouter()
    _dedup: WebhookDedup = dedup if dedup is not None else InMemoryWebhookDedup()

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

        if inbound.provider_message_id and not _dedup.claim(
            inbound.provider_message_id
        ):
            logger.debug(
                "WhatsApp inbound dedup hit: %s", inbound.provider_message_id
            )
            return {"status": "duplicate"}

        await on_message(inbound)
        return {"status": "accepted"}

    return router
