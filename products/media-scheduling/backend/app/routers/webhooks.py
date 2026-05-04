"""WAHA inbound webhook receiver.

Wires the seed surfaces end-to-end:

  1. `noctusai_lib.security.webhook_signatures.webhook_endpoint(...)` — HMAC-SHA256
     hex verification on the raw body via `X-Webhook-Hmac-SHA256`. Empty
     `WAHA_WEBHOOK_SECRET` → bypass-with-WARNING (early-dev affordance).
  2. `noctusai_lib.integrations.whatsapp.parse_waha_inbound_message` — strict
     parsing; ignored events return 200 with `{"status": "ignored"}`,
     malformed payloads → 400.
  3. `app.services.lid_auth.LidAuthService` — product-side LID-aware
     resolution + pending-LID capture (accept-with-rationale; see service docstring).
  4. `noctusai_lib.domain.chatbot.ConversationBufferService.buffer_inbound` — Redis
     buffer + debounce. Worker drains via the seed `ConversationWorker` shell.

Frontend contract (unchanged from Phase 5 hooks): NONE — this is the
WAHA inbound surface, not a frontend-facing route.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    QueuedConversationMessage,
)
from noctusai_lib.integrations.redis import (
    make_fake_redis_client,
    make_redis_client,
)
from noctusai_lib.integrations.whatsapp import (
    WahaIgnoredEvent,
    WahaPayloadError,
    parse_waha_inbound_message,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    static_secret_resolver,
    webhook_endpoint,
)

from app.config import settings
from app.database import get_supabase_client
from app.services.lid_auth import LidAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# --- Module-state caches (lazy; survive across requests) -----------------

_redis_client = None
_buffer_service: ConversationBufferService | None = None


def _get_buffer_service() -> ConversationBufferService:
    """Lazy buffer-service factory.

    Real Redis when `redis_url` set; in-memory fake otherwise (dev / tests).
    The fake keeps the webhook end-to-end-functional in unconfigured envs;
    the worker won't see the buffered messages (different process / different
    fake instance) but the webhook still validates + parses + responds.
    """
    global _redis_client, _buffer_service
    if _buffer_service is not None:
        return _buffer_service
    if settings.redis_url:
        _redis_client = make_redis_client(settings.redis_url)
    else:
        logger.warning(
            "webhooks: REDIS_URL unset — buffering inbound to in-memory fake "
            "(worker will NOT see these messages cross-process)"
        )
        _redis_client = make_fake_redis_client()
    _buffer_service = ConversationBufferService(
        _redis_client,
        memory_ttl_seconds=settings.conversation_memory_ttl_seconds,
        debounce_seconds=settings.message_debounce_seconds,
        idle_timeout_seconds=settings.conversation_idle_timeout_seconds,
        stream_maxlen=settings.redis_stream_maxlen,
    )
    return _buffer_service


# --- Per-request secret resolver -----------------------------------------


async def _resolve_waha_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Per-request lookup so test-time monkeypatches on `settings` are honored
    (avoids the import-time-capture trap; matches mailing's resend pattern)."""
    return ResolvedSecret(secret=settings.waha_webhook_secret or None)


# --- Endpoint ------------------------------------------------------------


@router.post("/waha")
async def receive_waha_message(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_waha_secret,
        scheme="sha256_hex",
        signature_header="X-Webhook-Hmac-SHA256",
        bypass_when_unset=True,
        log_prefix="waha-webhook",
    ),
) -> dict[str, str]:
    """WAHA inbound — receive one message, persist via buffer, schedule a reply.

    Flow:
      1. HMAC verified upstream (the dependency); body in `verified.body`.
      2. Parse the payload — `WahaIgnoredEvent` returns 200 with `ignored`;
         `WahaPayloadError` raises 400 (provider mistake, not auth).
      3. LID-aware authorization lookup; unknown LIDs land in
         `pending_chat_identities` so admins can resolve them later.
      4. Push the inbound onto `ConversationBufferService.buffer_inbound`.
         Worker (separate process / lifespan task) drains the debounce
         queue and dispatches to the LLM.
      5. Reply payload tells WAHA whether we accepted or rejected the
         user — the actual GPT reply is sent later by the worker via
         `whatsapp_client.send_text(...)`.

    Returns:
      `{"status": "accepted"|"rejected"|"ignored", "reply": "<short text>"}`.

    Audit + replay-window enforcement live in the seed dep. We don't add
    any side-channel writes here — keep the webhook response sub-second.
    """
    body = verified.body
    try:
        raw_payload: dict[str, Any] = json.loads(body) if body else {}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if settings.waha_log_raw_webhooks:
        logger.info("waha-webhook: raw payload=%s", raw_payload)

    try:
        inbound = parse_waha_inbound_message(raw_payload)
    except WahaIgnoredEvent as exc:
        # Ignored events (status updates, message-acks, etc.) — silent OK
        # is wrong here; log at info so we can audit volume.
        logger.info("waha-webhook: ignored event: %s", exc)
        return {"status": "ignored", "reply": ""}
    except WahaPayloadError as exc:
        logger.warning("waha-webhook: payload error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Authorization lookup (LID-aware). Admin client per PROJECT.md §6
    # Phase 2 RLS — webhook path runs as service_role, bypasses RLS.
    admin_db = get_supabase_client()
    auth = LidAuthService(admin_db)
    user = auth.authorized_user_for_chat_id(
        inbound.chat_id, from_phone=inbound.from_phone, push_name=inbound.from_name
    )

    if user is None and inbound.chat_id and "@lid_" in inbound.chat_id:
        # Unknown LID — park for admin resolution. Best-effort; failure
        # logged inside the service, webhook keeps going.
        auth.capture_pending_lid(
            inbound.chat_id,
            push_name=inbound.from_name,
            phone_hint=inbound.from_phone or None,
        )

    metadata: dict[str, Any] = {"authorized": user is not None}
    if inbound.chat_id:
        metadata["chat_id"] = inbound.chat_id
    if inbound.from_name:
        metadata["from_name"] = inbound.from_name
    if inbound.media is not None:
        metadata["media_url"] = inbound.media.url
        metadata["media_mimetype"] = inbound.media.mimetype

    buffer_service = _get_buffer_service()
    buffer_service.buffer_inbound(
        QueuedConversationMessage(
            conversation_id=inbound.from_phone,
            text=inbound.text,
            direction="inbound",
            provider_message_id=inbound.provider_message_id,
            user_id=user["id"] if user else None,
            metadata=metadata,
        ),
        # Trigger an LLM reply when the message has text content; for
        # media-only inbounds the worker will pick them up on the next
        # text follow-up. Keeps the seed contract simple — full
        # transcription/vision lives in the worker.
        trigger_reply=bool(inbound.text),
    )

    if user is None:
        return {
            "status": "rejected",
            "reply": "Este número ainda não está autorizado para agendamentos.",
        }
    return {
        "status": "accepted",
        "reply": "Recebi sua solicitação. Vou validar os dados do agendamento.",
    }
