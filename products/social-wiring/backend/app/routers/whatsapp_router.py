"""WhatsApp inbound webhook — WAHA forwards messages here.

This router handles incoming WhatsApp messages from WAHA. It validates
the sender against the authorized whitelist, then routes the message
through the :class:`WhatsAppIntakeService` conversation state machine.

Only text messages are processed; media messages are acknowledged but
not acted on (future: image/video attachments could be an alternate
upload path).

Auth note: this endpoint does NOT use the standard JWT auth because
WAHA's webhook calls carry no Authorization header. Sender validation
is handled by the phone number whitelist in settings. The endpoint
itself is public but useless without a valid WAHA instance forwarding
real messages.
"""
from __future__ import annotations

import logging
import hmac
import hashlib
import json
from pathlib import Path
from uuid import UUID

import redis
from fastapi import APIRouter, Request, Response, status

from noctusai_lib.domain.chatbot import QueuedConversationMessage

from app.config import settings
from app.dependencies import get_admin_client
from app.schemas.whatsapp import WAHAMessage, WAHAMessagePayload, WAHASessionStatusPayload
from app.services.conversation_module import get_conversation_module
from app.services.credential_store import CredentialStore, EncryptionNotConfigured
from app.services.crm_service import CRMNotConfigured, CRMService
from app.services.media_service import ResolvedMedia, make_media_service
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.waha_response_registry import record_waha_sample
from app.services.whatsapp_chatbot_service import WhatsAppChatbotService
from app.services.whatsapp_intake_service import WhatsAppIntakeService
from app.services.youtube_service import YouTubeService, YouTubeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

_UPLOAD_DIR = Path("/tmp/uploads")


def _build_intake_service() -> WhatsAppIntakeService | None:
    """Wire the intake service. Returns None when critical config is
    missing — the webhook will 200-ack but not process messages."""
    authorized = [
        n.strip()
        for n in settings.whatsapp_authorized_numbers.split(",")
        if n.strip()
    ]
    if not authorized:
        logger.warning(
            "whatsapp_authorized_numbers is empty — WhatsApp inbound disabled"
        )
        return None

    admin_supabase = get_admin_client()

    # Redis for conversation state
    try:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
    except Exception as exc:
        logger.error("Redis unavailable for WhatsApp state: %s", exc)
        return None

    # YouTube service (required only when an upload is confirmed). Keep chat
    # online so the assistant can tell the user what is missing.
    youtube: YouTubeService | None = None
    try:
        store = CredentialStore(admin_supabase, settings.encryption_key)
        youtube = YouTubeService(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=settings.youtube_redirect_uri,
            credential_store=store,
        )
    except (EncryptionNotConfigured, YouTubeServiceError) as exc:
        logger.warning("YouTube service unavailable for WhatsApp upload confirmation: %s", exc)

    # CRM (optional — degrades to manual title)
    crm: CRMService | None = None
    try:
        crm = CRMService(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except CRMNotConfigured:
        logger.info("CRM not configured — WhatsApp uploads will use manual titles")

    # Org ID — for WhatsApp uploads we use a default org since there's no
    # JWT context. The first org that connected YouTube is used.
    # In a single-tenant deployment this is the only org.
    org_id = _resolve_default_org(admin_supabase)
    if org_id is None:
        logger.warning(
            "No YouTube credentials found; WhatsApp chat remains enabled, "
            "but upload confirmation will be blocked until YouTube is connected"
        )
        org_id = UUID(settings.local_dev_org_id)

    return WhatsAppIntakeService(
        waha_base_url=settings.waha_base_url,
        waha_api_key=settings.waha_api_key,
        waha_session=settings.waha_session,
        redis_client=redis_client,
        authorized_numbers=authorized,
        crm_service=crm,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
        upload_dir=_UPLOAD_DIR,
        org_id=org_id,
    )


async def build_intake_service_for_processor(
    *,
    admin_supabase: object | None = None,
    org_id: UUID | None = None,
) -> WhatsAppIntakeService | None:
    """Async public alias of ``_build_intake_service`` for the
    conversation worker's processor.

    The processor runs in a worker thread but dispatches into the main
    asyncio loop via ``run_coroutine_threadsafe`` — once on the loop, it
    can call this normally. Args are accepted for forward-compat with a
    future refactor that passes the lifespan-resolved admin client + org
    id directly; today the underlying ``_build_intake_service`` resolves
    both on its own.
    """
    # admin_supabase + org_id reserved for a future signature; pass-through
    # is intentional so callers don't break when we tighten the contract.
    del admin_supabase, org_id
    return _build_intake_service()


def _resolve_default_org(admin_supabase) -> UUID | None:
    """Find the first org that has YouTube credentials connected.

    In the single-channel setup this returns the only org. Multi-tenant
    would need a mapping table or a WhatsApp-to-org lookup.
    """
    try:
        response = (
            admin_supabase
            .schema("social_wiring")
            .table("credentials")
            .select("org_id")
            .eq("provider", "youtube")
            .limit(1)
            .execute()
        )
        if response.data:
            return UUID(response.data[0]["org_id"])
    except Exception as exc:
        logger.error("failed to resolve default org: %s", exc)
    return None


@router.post("/webhook")
async def whatsapp_webhook(request: Request) -> Response:
    """WAHA webhook endpoint.

    Always returns 200 to prevent WAHA from retrying. Processing
    failures are logged but never surfaced as HTTP errors — WAHA
    doesn't understand them and would just retry indefinitely.
    """
    raw_body = await request.body()
    if settings.waha_webhook_hmac_secret:
        signature = request.headers.get("X-Webhook-Hmac-SHA256", "")
        expected = hmac.new(
            settings.waha_webhook_hmac_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("WhatsApp webhook rejected: invalid HMAC signature")
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return Response(status_code=status.HTTP_200_OK)
    record_waha_sample(
        source="webhook",
        direction="waha_to_app",
        event_type=str(body.get("event") or "unknown") if isinstance(body, dict) else "unknown",
        payload=body,
        handling_notes=(
            "Webhook envelopes are always 200-acknowledged. Process only inbound "
            "message/message.any payloads with fromMe=false and text body; log "
            "session.status; ignore unknown events safely."
        ),
    )

    try:
        envelope = WAHAMessagePayload.model_validate(body)
    except Exception:
        logger.debug("WhatsApp webhook ignored: unknown WAHA envelope")
        return Response(status_code=status.HTTP_200_OK)

    # WAHA sends various event types. We process inbound messages and log
    # session.status so deploy testing can diagnose QR/login state.
    event = envelope.event
    if event == "session.status":
        payload = envelope.payload
        if isinstance(payload, WAHASessionStatusPayload):
            logger.info(
                "WAHA session %s status: %s",
                envelope.session,
                payload.status,
            )
        return Response(status_code=status.HTTP_200_OK)

    if event not in {"message", "message.any"}:
        return Response(status_code=status.HTTP_200_OK)

    payload = envelope.payload
    if not isinstance(payload, WAHAMessage):
        return Response(status_code=status.HTTP_200_OK)

    # Extract sender and message body
    sender = payload.from_ or payload.chat_id
    message_body = payload.body or ""

    if not sender:
        return Response(status_code=status.HTTP_200_OK)

    if payload.from_me:
        return Response(status_code=status.HTTP_200_OK)

    # Fast dedup pre-filter — Redis SETNX on the provider_message_id
    # so the SECOND of (message, message.any) doesn't pay the OpenAI
    # cost. Uses its own short-lived Redis connection so we can run
    # this BEFORE building the heavy intake service. The
    # conversation_messages UNIQUE constraint is the durable backstop
    # for restart-survival; this SETNX is purely for cost + latency.
    provider_message_id = (payload.id or "").strip()
    if provider_message_id:
        try:
            _setnx_client = redis.from_url(settings.redis_url, decode_responses=True)
            seen_key = f"whatsapp:msg_seen:{provider_message_id}"
            won = _setnx_client.set(seen_key, "1", ex=5 * 60, nx=True)
            if not won:
                logger.info(
                    "WhatsApp inbound duplicate via SETNX (event=%s, id=%s)",
                    event,
                    provider_message_id,
                )
                return Response(status_code=status.HTTP_200_OK)
        except Exception:
            logger.exception("SETNX dedup check failed; falling through to DB dedup")

    # Media-aware inbound: if the payload carries media (audio note,
    # photo, video, document), resolve it to enriched text BEFORE the
    # chatbot ever sees the message. This is the difference between
    # "audio recebido — não suportado" and "[Audio transcrito] ola tudo
    # bem? gostaria de saber sobre o ONE5555".
    resolved_media: ResolvedMedia | None = None
    media_obj = payload.media if isinstance(payload.media, object) else None
    media_url = None
    media_mimetype = None
    media_filename = None
    if payload.has_media and isinstance(payload.media, object):
        # WAHAMedia is a Pydantic model with .url / .mimetype / .filename;
        # falls back to dict when payload arrives as plain dict shape.
        media_url = getattr(payload.media, "url", None) or (
            payload.media.get("url") if isinstance(payload.media, dict) else None
        )
        media_mimetype = getattr(payload.media, "mimetype", None) or (
            payload.media.get("mimetype") if isinstance(payload.media, dict) else None
        )
        media_filename = getattr(payload.media, "filename", None) or (
            payload.media.get("filename") if isinstance(payload.media, dict) else None
        )
    if media_url and settings.openai_api_key:
        try:
            media_service = make_media_service()
            resolved_media = await media_service.resolve_inbound(
                url=media_url,
                mimetype=media_mimetype,
                filename=media_filename,
                fallback_text=message_body,
            )
            # Merge any caption text the user typed alongside the media.
            if message_body and resolved_media.text:
                message_body = f"{resolved_media.text}\n\nLegenda do usuario: {message_body}"
            else:
                message_body = resolved_media.text or message_body
        except Exception:
            logger.exception("media resolution failed for %s", sender)

    if not message_body:
        # No text, no resolvable media → nothing meaningful for the
        # chatbot to react to. ACK and move on.
        return Response(status_code=status.HTTP_200_OK)

    # Build the intake service
    intake = _build_intake_service()
    if intake is None:
        logger.debug("WhatsApp intake not configured — dropping message")
        return Response(status_code=status.HTTP_200_OK)

    # Durable dedup oracle — the SETNX pre-filter above caught the
    # in-memory race; the conversation_messages.provider_message_id
    # UNIQUE constraint survives container restarts. Anything that
    # passes SETNX also passes this in 99.9% of cases; the one
    # exception is a 5-minute SETNX TTL expiring before a delayed
    # WAHA retry, in which case the DB catch fires.
    message_store = MessageStore(admin_supabase=get_admin_client(), org_id=intake._org_id)
    try:
        message_store.record(
            session_id=intake.canonical_session_id(sender),
            raw_sender=sender,
            direction="inbound",
            body=message_body,
            provider_message_id=provider_message_id or None,
            authorized=True,
            structured_payload=resolved_media.structured_payload if resolved_media else None,
        )
    except DuplicateMessage:
        logger.info(
            "WhatsApp inbound duplicate (event=%s, id=%s) — dropped",
            event,
            provider_message_id,
        )
        return Response(status_code=status.HTTP_200_OK)
    except Exception:
        # A persistence error must NOT block the bot from replying — log
        # loudly and proceed. The Redis memory list still carries recall.
        logger.exception("conversation_messages insert failed; processing anyway")

    # Auth check — unauthorized senders get a polite reply (not silent drop).
    # Once-per-conversation guard via Redis so we don't spam a denial loop
    # against a stranger blasting messages; first contact gets the reply,
    # subsequent inbounds in a 24h window are quietly logged.
    if not intake.is_authorized(sender):
        already_notified = False
        try:
            denied_key = f"whatsapp:denied:{sender}"
            already_notified = intake.redis_client.get(denied_key) is not None
            if not already_notified:
                intake.redis_client.set(denied_key, "1", ex=24 * 3600)
        except Exception:
            logger.exception("failed to read/set denied marker for %s", sender)
        logger.info(
            "WhatsApp message from unauthorized number %s — replying=%s",
            sender,
            not already_notified,
        )
        if not already_notified:
            try:
                await intake.send_reply(
                    sender,
                    (
                        "Olá! 👋 Este número não está na lista de autorizados "
                        "para usar o agente da NoctusAI.\n\n"
                        "Se você acredita que deveria ter acesso, fale com a "
                        "equipe NoctusAI para incluir seu número.\n\n"
                        "Até mais!"
                    ),
                )
            except Exception:
                logger.exception("failed to send unauthorized reply to %s", sender)
        return Response(status_code=status.HTTP_200_OK)

    # Normalize the sender to a canonical session id (phone-form when we
    # know the LID→phone mapping, raw otherwise). One conversation, one
    # memory key — see WhatsAppIntakeService.canonical_session_id for why.
    canonical_session = intake.canonical_session_id(sender)

    # Process the message
    try:
        if settings.whatsapp_chatbot_enabled and settings.openai_api_key:
            # Buffer the inbound into the seed conversation buffer; the
            # ConversationWorker drains the queue after the debounce
            # window (settings.message_debounce_seconds, default 8s).
            # Multi-message intents — code in one msg, drive URL in the
            # next — accumulate naturally and get processed in a single
            # worker tick. The processor decides regex-fast-path vs
            # LLM fallback based on what's in the buffer.
            module = get_conversation_module()
            if module is not None:
                module.buffer.buffer_inbound(
                    QueuedConversationMessage(
                        conversation_id=canonical_session,
                        text=message_body,
                        direction="inbound",
                        provider_message_id=provider_message_id or None,
                        metadata={"raw_sender": sender},
                    )
                )
                logger.info(
                    "WhatsApp inbound buffered: sender=%s conv=%s debounce=%ss",
                    sender,
                    canonical_session,
                    settings.message_debounce_seconds,
                )
            else:
                # Conversation module not wired (lifespan startup
                # short-circuited — likely missing admin client). Fall
                # back to the legacy inline path so the bot still replies,
                # just without multi-message accumulation.
                logger.warning(
                    "Conversation module unavailable; using inline chatbot for sender=%s",
                    sender,
                )
                chatbot = WhatsAppChatbotService(
                    redis_client=intake.redis_client,
                    intake_service=intake,
                    session_id=canonical_session,
                    model=settings.openai_chat_model,
                    api_key=settings.openai_api_key,
                )
                reply = await chatbot.reply(message_body)
                if reply:
                    await intake.send_reply(sender, reply)
        else:
            await intake.handle_message(sender, message_body)
    except Exception:
        logger.exception(
            "WhatsApp intake failed for sender=%s", sender
        )

    return Response(status_code=status.HTTP_200_OK)


__all__ = ["router"]
