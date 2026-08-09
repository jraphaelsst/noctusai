"""WhatsApp inbound webhook — WAHA forwards messages here.

This router handles incoming WhatsApp events from WAHA. It validates the
sender against the authorized whitelist, then routes the message through
the :class:`WhatsAppIntakeService` conversation state machine. Postgres
(``social_wiring.conversation_messages`` + ``whatsapp_chats``, migration
040) is the read source of truth for the chat inbox — every event this
router handles that changes what a client should see is persisted BEFORE
it is published on the realtime bus.

Events handled (WAHA webhook subscription list, wired at connection-create
time by ``whatsapp_connections_router.py``):

  ``message`` / ``message.any``
      Inbound text (+ media, resolved to text). Persisted, folded into
      ``whatsapp_chats`` via ``WhatsAppChatStore.record_message``, and
      published as ``message.new`` + ``chat.upsert``. WAHA fires both
      ``message`` and ``message.any`` for the same inbound — the Redis
      SETNX pre-filter plus the ``UNIQUE(provider_message_id)`` constraint
      guard the race; keep both.
  ``message.ack``
      Delivery/read receipt for a message we sent or received. Applied to
      the matching row by ``provider_message_id`` (globally unique — no
      org/connection context needed) and published as ``message.ack``. An
      ack for a message we haven't recorded yet is a no-op, never an error.
  ``message.reaction``
      Acknowledged (200) but not persisted — no schema column exists yet
      for reactions. See the ``NOC-REMEDIATE[whatsapp-reaction-persistence]``
      marker at the handling site.
  ``session.status``
      QR/login state. Persisted to Redis (no durable column exists on
      ``whatsapp_connections`` for this — see ``_handle_session_status``)
      and published as ``session.status`` so the connection UI can react
      live instead of polling ``GET /connections/{id}/status`` (a ~13s
      live WAHA round-trip).

Only text messages are processed for the chatbot/intake flow; media
messages are resolved to text via ``media_service`` when an OpenAI key is
configured, else acknowledged but not acted on.

Auth note: these endpoints do NOT use the standard JWT auth because
WAHA's webhook calls carry no Authorization header. Signature verification
is via ``noctusai_lib.security.webhook_signatures.webhook_endpoint`` (HMAC
``sha256_hex`` scheme, ``X-Webhook-Hmac-SHA256`` header — WAHA's shape);
sender validation is a SEPARATE, later gate: the phone number whitelist in
settings / the per-connection ``authorized_numbers``.

Two receiver routes are provided:

  POST /api/whatsapp/webhook
      Legacy global route (back-compat). Uses the product-level HMAC
      secret from settings when set; bypasses (with a WARNING) when unset.

  POST /api/whatsapp/webhook/{token}
      Per-connection token-scoped route. The token is an opaque secret
      minted on connection create; it resolves to a specific connection
      record (org / user / session). Unknown token → generic 404 (no
      token enumeration). HMAC check uses the same global HMAC secret
      when configured. Processing delegates to the shared
      ``_process_waha_body`` helper — identical pipeline, no forked logic.
"""
# 🔴 NO `from __future__ import annotations` IN THIS FILE — deliberate.
#
# This module carries `@limiter.limit(...)` routes. slowapi resolves a
# rate-limited endpoint's signature at runtime; under PEP 563 every
# annotation is a STRING, so FastAPI/slowapi can no longer see a Pydantic
# body model and the route breaks. Keeper: `check_slowapi_with_pep563`
# (`mcp/noctusai/tools/noctus/dev/compliance.py`), baseline = zero.
#
# Today's two rate-limited routes take only `request: Request` + a
# `webhook_endpoint(...)` dependency and no body model, so the import was a
# LATENT hazard rather than a live break — it would have detonated the day
# someone added a request body. Removed rather than annotated, matching how
# the other baseline cases were fixed (products/seed .../webhook_router.py,
# products/adconnect .../financial.py both carry no future-import).

import asyncio
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, Request, Response, status

from noctusai_lib.domain.chatbot import QueuedConversationMessage
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import get_admin_client, get_settings
from app.rate_limit import limiter
from app.schemas.whatsapp import WAHAMessage, WAHAMessagePayload, WAHASessionStatusPayload
from app.services.conversation_module import get_conversation_module
from app.services.credential_vault import EncryptionNotConfigured
from app.services.account_credentials import build_youtube_service_for_org
from noctusai_lib.integrations.vista import (
    VistaNotConfigured as CRMNotConfigured,
    VistaRESTAdapter as CRMService,
)
from app.services.media_service import ResolvedMedia, make_media_service
from app.services.message_store import DuplicateMessage, MessageStore, StoredMessage
from app.modules.email_marketing.services.contact_service import ContactService
from app.services.waha_response_registry import record_waha_sample
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_chatbot_service import WhatsAppChatbotService
from app.services.whatsapp_identity import resolve_identity
from app.services.whatsapp_intake_service import WhatsAppIntakeService
from app.services.whatsapp_connection_store import build_whatsapp_connection_store
from app.services.whatsapp_realtime import (
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
    get_whatsapp_bus,
    publish_whatsapp_event,
)
from app.modules.youtube.services.youtube import YouTubeService, YouTubeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# ── Background contact auto-registration ──────────────────────────────────────
# 🔴 BOUNDARY: identity resolution hits WAHA (get_lid_phone + get_contact). It
# MUST NOT run on the inbound reply hot path — a slow WAHA there delayed/killed
# the AI reply (2026-06-24 regression). We fire-and-forget it so the reply is
# dispatched immediately; the resolved {phone, lids, name} lands in
# social_wiring.contacts for the read endpoints. WAHA calls are bounded by the
# seed client's short read timeout; any failure is swallowed with a warning.
_bg_tasks: set = set()


def _cfg_for_request(request: Request):
    """Resolve settings the way FastAPI would, for callables that cannot
    take ``Depends(get_settings)``.

    ``_resolve_waha_secret`` is handed to ``webhook_endpoint(...)`` as a
    plain ``(request, body)`` callable, so its signature is fixed and it
    cannot declare a dependency. Reading the module singleton directly is
    what forced tests to `monkeypatch.setattr(settings, ...)` — the
    self-patch this router regressed on. Consulting
    ``app.dependency_overrides`` honours the SAME `get_settings` seam the
    rest of the product uses, so `override_settings` works here too and
    tests never touch the singleton.

    → KB § PATTERNS/backend/di-test-seam.md (Class-A)
    """
    override = request.app.dependency_overrides.get(get_settings)
    return override() if override is not None else settings


def _fire_and_forget(coro) -> None:
    """Schedule a coroutine without blocking the caller; hold a ref vs GC."""
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:
        # No running loop (e.g. a sync test context) — not hot-path critical.
        coro.close()
        return
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _register_contact_bg(
    *,
    base_url: str,
    api_key: str | None,
    session: str,
    sender: str,
    push_name: str | None,
    org_id: str,
) -> None:
    """Resolve a sender's WhatsApp identity + upsert a contact. OFF the hot path."""
    try:
        from noctusai_lib.integrations.whatsapp import get_whatsapp_client  # noqa: PLC0415

        waha = get_whatsapp_client(base_url=base_url, api_key=api_key, session=session)
        identity = await resolve_identity(waha, sender)
        if identity.phone:
            ContactService(
                db=get_admin_client(), org_id=org_id
            ).upsert_whatsapp_contact(
                phone=identity.phone,
                lids=identity.lids,
                name=identity.name or push_name or None,
                jid=identity.jid,
            )
    except Exception:
        logger.warning(
            "WhatsApp contact auto-register failed for sender=%s — continuing",
            sender,
            exc_info=True,
        )


_UPLOAD_DIR = Path("/tmp/uploads")


def _build_intake_service(*, connection=None, cfg=None) -> WhatsAppIntakeService | None:
    """Wire the intake service. Returns None when critical config is
    missing — the webhook will 200-ack but not process messages.

    When ``connection`` is a :class:`WhatsAppConnectionRecord` (per-connection
    token-scoped route, migration 016):
      - ``authorized_numbers`` comes from the connection record.
        Empty list = allow ALL senders (per-connection default — differs from
        the global env var where empty means DISABLED).
      - ``bound_chats`` comes from the connection record.
      - ``connection_id`` is derived from ``connection.id``.

    When ``connection`` is None (legacy global route):
      - ``authorized_numbers`` comes from ``settings.whatsapp_authorized_numbers``
        (comma-separated env var).  Empty = DISABLED → returns None.
      - ``bound_chats`` is None (all chats listened to).
      - ``connection_id`` is None.
    """
    cfg = cfg or settings
    if connection is not None:
        # Per-connection route: empty list = allow all (NOT disabled).
        authorized = list(connection.authorized_numbers or [])
        bound_chats: list[dict] | None = list(connection.bound_chats or [])
        _connection_id = connection.id
    else:
        # Legacy global route: empty = disabled.
        authorized = [
            n.strip()
            for n in cfg.whatsapp_authorized_numbers.split(",")
            if n.strip()
        ]
        bound_chats = None
        _connection_id = None
        if not authorized:
            logger.warning(
                "whatsapp_authorized_numbers is empty — WhatsApp inbound disabled"
            )
            return None

    admin_supabase = get_admin_client()

    # Redis for conversation state
    try:
        redis_client = redis.from_url(cfg.redis_url, decode_responses=True)
        redis_client.ping()
    except Exception as exc:
        logger.error("Redis unavailable for WhatsApp state: %s", exc)
        return None

    # YouTube service (required only when an upload is confirmed). Keep chat
    # online so the assistant can tell the user what is missing.
    youtube: YouTubeService | None = None
    try:
        youtube = build_youtube_service_for_org(admin_supabase, settings)
    except (EncryptionNotConfigured, YouTubeServiceError) as exc:
        logger.warning("YouTube service unavailable for WhatsApp upload confirmation: %s", exc)

    # CRM (optional — degrades to manual title)
    crm: CRMService | None = None
    try:
        crm = CRMService(
            base_url=cfg.crm_base_url,
            api_key=cfg.crm_api_key,
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
        org_id = UUID(cfg.local_dev_org_id)

    return WhatsAppIntakeService(
        waha_base_url=cfg.waha_base_url,
        waha_api_key=cfg.waha_api_key,
        waha_session=cfg.waha_session,
        redis_client=redis_client,
        authorized_numbers=authorized,
        crm_service=crm,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
        upload_dir=_UPLOAD_DIR,
        org_id=org_id,
        connection_id=_connection_id,
        bound_chats=bound_chats,
    )


async def build_intake_service_for_processor(
    *,
    admin_supabase: object | None = None,
    org_id: UUID | None = None,
    connection=None,
    cfg=None,
) -> WhatsAppIntakeService | None:
    """Async public alias of ``_build_intake_service`` for the
    conversation worker's processor.

    The processor runs in a worker thread but dispatches into the main
    asyncio loop via ``run_coroutine_threadsafe`` — once on the loop, it
    can call this normally. Args are accepted for forward-compat with a
    future refactor that passes the lifespan-resolved admin client + org
    id directly; today the underlying ``_build_intake_service`` resolves
    both on its own.

    ``connection`` (migration 016): optional :class:`WhatsAppConnectionRecord`
    to forward per-connection ``authorized_numbers`` / ``bound_chats`` config.
    """
    # admin_supabase + org_id reserved for a future signature; pass-through
    # is intentional so callers don't break when we tighten the contract.
    del admin_supabase, org_id
    return _build_intake_service(connection=connection, cfg=cfg)


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


async def _handle_session_status(envelope: WAHAMessagePayload, *, connection, cfg=None) -> None:
    """Persist + publish a ``session.status`` event.

    No durable column exists on ``whatsapp_connections`` for session state
    — adding one is out of this slice's territory (that table's router +
    schema belong to a peer branch). Redis is the persistence layer
    instead: a ``whatsapp:session_status:{connection_id|session}`` key
    with a 24h TTL, keyed by connection when we have one (token route)
    else by WAHA session name (legacy route). This is what lets a future
    connection-status read replace the current live-WAHA poll
    (``GET /connections/{id}/status``, a ~13s round-trip) — out of THIS
    router's scope, but the durable half of that fix. The realtime publish
    below is the half that's in scope: it lets a subscribed client react
    immediately instead of polling at all.
    """
    cfg = cfg or settings
    payload = envelope.payload
    if not isinstance(payload, WAHASessionStatusPayload):
        return
    status_value = payload.status or ""
    logger.info("WAHA session %s status: %s", envelope.session, status_value)

    key = f"whatsapp:session_status:{connection.id if connection is not None else envelope.session}"
    try:
        _status_redis = redis.from_url(cfg.redis_url, decode_responses=True)
        _status_redis.set(key, status_value, ex=24 * 3600)
    except Exception:
        logger.exception("failed to persist WAHA session status (key=%s)", key)

    if connection is not None:
        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=connection.id,
            event=EVENT_SESSION_STATUS,
            payload={"status": status_value, "session": envelope.session},
        )


async def _handle_message_ack(envelope: WAHAMessagePayload, *, connection, cfg=None) -> None:
    """Apply a ``message.ack`` delivery/read receipt and publish it.

    WAHA reuses the message shape for acks (``id`` / ``ack`` / ``from`` /
    ...), so ``envelope.payload`` already resolves to :class:`WAHAMessage`
    — no dedicated ack schema needed.

    ``org_id`` is required to construct a :class:`MessageStore` but is NOT
    used to scope the update (see ``MessageStore.apply_ack``'s docstring —
    ``provider_message_id`` is globally unique): the connection's org when
    known, else the dev-fallback org, exactly as ``_build_intake_service``
    falls back for the legacy route.
    """
    cfg = cfg or settings
    payload = envelope.payload
    if not isinstance(payload, WAHAMessage):
        return
    provider_message_id = (payload.id or "").strip()
    if not provider_message_id:
        return
    try:
        ack = int(payload.ack) if payload.ack is not None else None
    except (TypeError, ValueError):
        ack = None
    if ack is None:
        logger.debug("WhatsApp ack event with unparseable ack=%r — dropped", payload.ack)
        return

    org_id = connection.org_id if connection is not None else UUID(cfg.local_dev_org_id)
    message_store = MessageStore(admin_supabase=get_admin_client(), org_id=org_id)
    acked_at = datetime.now(timezone.utc).isoformat()
    updated = message_store.apply_ack(
        provider_message_id=provider_message_id, ack=ack, acked_at=acked_at
    )
    if updated is None:
        # Ack arrived before our insert (or for a message this store never
        # recorded) — a no-op, never an error. WAHA will not retry a 200.
        logger.info(
            "WhatsApp ack for unknown message (provider_message_id=%s) — no-op",
            provider_message_id,
        )
        return

    # Scope the publish by the message's OWN connection_id (read back off
    # the row), NOT the webhook route's connection context — an ack can
    # legitimately arrive on the legacy route for a message a token-route
    # connection recorded, and the row is the source of truth for which
    # line owns it.
    if updated.connection_id is not None:
        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=updated.connection_id,
            event=EVENT_MESSAGE_ACK,
            payload={
                "chat_id": updated.chat_id,
                "provider_message_id": updated.provider_message_id,
                "ack": updated.ack,
                "acked_at": updated.acked_at,
            },
        )


async def _process_waha_body(
    body: dict,
    *,
    event_source: str = "webhook",
    connection=None,
    cfg=None,
) -> Response:
    """Shared WAHA envelope processor.

    Handles envelope validation, event routing, dedup (Redis SETNX + DB),
    media resolution, auth check, and message dispatch. Called by both the
    legacy global route and the per-connection token-scoped route so the
    logic is not forked.

    ``event_source`` is used for WAHA sample recording / log context only
    (e.g. ``"webhook"`` or ``"webhook/token"``).

    ``connection`` is a :class:`WhatsAppConnectionRecord` resolved from the
    per-connection token-scoped route.  When present:
      - Inbound messages are tagged ``connection_id=connection.id``.
      - The chatbot auto-reply fires ONLY when ``connection.auto_reply_enabled``
        is True (default OFF — locked product decision for manual chat testing).
    When absent (legacy global route) the old behaviour is preserved: inbound
    messages are stored without connection_id and auto-reply is gated only on
    ``cfg.whatsapp_chatbot_enabled``.

    Always returns a ``200 OK`` Response (WAHA doesn't understand our errors
    and would retry indefinitely on non-200; processing failures are logged).
    """
    cfg = cfg or settings
    record_waha_sample(
        source=event_source,
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

    # WAHA sends several event types; each is handled explicitly so an
    # unrecognized future event falls through to the safe "ignore" branch
    # below rather than silently misrouting into one of these.
    event = envelope.event

    if event == "session.status":
        await _handle_session_status(envelope, connection=connection, cfg=cfg)
        return Response(status_code=status.HTTP_200_OK)

    if event == "message.ack":
        await _handle_message_ack(envelope, connection=connection, cfg=cfg)
        return Response(status_code=status.HTTP_200_OK)

    if event == "message.reaction":
        # NOC-REMEDIATE[whatsapp-reaction-persistence]: no schema column
        # exists for reactions yet — migration 040 added ack/acked_at/chat_id
        # but not a reactions surface. Ack-and-drop until a product need for
        # reaction data emerges. — 2026-08-03
        logger.debug(
            "WhatsApp reaction event received (session=%s) — acknowledged, not persisted",
            envelope.session,
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
            _setnx_client = redis.from_url(cfg.redis_url, decode_responses=True)
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
    if media_url and cfg.openai_api_key:
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

    # Build the intake service — pass the full connection record so per-connection
    # authorized_numbers and bound_chats config (migration 016) is wired in.
    intake = _build_intake_service(connection=connection, cfg=cfg)
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
    chat_id = payload.chat_id or sender
    stored_message: StoredMessage | None = None
    try:
        stored_message = message_store.record(
            session_id=intake.canonical_session_id(sender),
            raw_sender=sender,
            direction="inbound",
            body=message_body,
            provider_message_id=provider_message_id or None,
            authorized=True,
            structured_payload=resolved_media.structured_payload if resolved_media else None,
            connection_id=connection.id if connection is not None else None,
            chat_id=chat_id,
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
        # `stored_message` stays None: there is nothing durable to fold
        # into the chats table or announce on the bus below (never publish
        # a write that didn't happen).
        logger.exception("conversation_messages insert failed; processing anyway")

    # ── Maintain the chats table + publish realtime events ──────────────────
    # Gated on `connection is not None`: WhatsAppChatStore rows are keyed by
    # (connection_id, chat_id) and connection_id is NOT NULL on that table
    # (migration 040) — the legacy global route has no connection to key by,
    # the same limitation the per-connection inbox already has for message
    # storage. Runs AFTER the DB write above — never before, a client must
    # never be told about a message that isn't durable yet — and only when
    # the write actually happened (`stored_message is not None`).
    if stored_message is not None and connection is not None:
        try:
            chat_summary = WhatsAppChatStore(
                admin_supabase=get_admin_client(), org_id=connection.org_id
            ).record_message(
                connection_id=connection.id,
                chat_id=chat_id,
                direction="inbound",
                body=message_body,
                created_at=stored_message.created_at or datetime.now(timezone.utc).isoformat(),
                # `pushName` is the only identity the inbound payload itself
                # carries; the store only ever FILLS a title in, never
                # overwrites a resolved one with a worse one (see its
                # docstring) — safe to pass on every message.
                title=getattr(payload, "pushName", None) or None,
                has_media=bool(resolved_media) or payload.has_media,
            )
        except Exception:
            logger.exception(
                "whatsapp_chats upsert failed for connection=%s chat=%s — inbox row "
                "may be stale; the message itself is already durable",
                connection.id, chat_id,
            )
            chat_summary = None

        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=connection.id,
            event=EVENT_MESSAGE_NEW,
            payload={"chat_id": chat_id, "message": stored_message.as_message_dto()},
        )
        if chat_summary is not None:
            await publish_whatsapp_event(
                bus,
                connection_id=connection.id,
                event=EVENT_CHAT_UPSERT,
                payload=chat_summary.as_dict(),
            )

    # ── Best-effort contact auto-registration ────────────────────────────────
    # For every inbound message, resolve the sender's identity and upsert
    # it into social_wiring.contacts.  Failure NEVER blocks message ingestion.
    # We need the WahaClient bound to this connection's credentials to call
    # the WAHA identity endpoints.
    # Fire-and-forget: resolve identity + upsert contact AFTER the reply path,
    # never blocking it (see _register_contact_bg). Decrypt is cheap + local;
    # the WAHA calls happen inside the backgrounded coroutine.
    if connection is not None:
        try:
            # drift-found (pre-existing, fixed on contact — 2 stacked bugs):
            # (1) this block used to read `connection.encrypted_api_key` —
            # a field WhatsAppConnectionRecord never carries (only the
            # store's raw row does). (2) it read `payload.pushName`
            # directly — Pydantic v2's `extra="allow"` does NOT synthesize
            # a `None` for an absent extra field; a payload with no
            # `pushName` key raises AttributeError on access, same as (1).
            # Both raised on effectively every real inbound, were swallowed
            # by this same `except Exception`, and logged a misleading
            # "scheduling failed" warning — contact auto-registration has
            # therefore never actually fired via the per-connection route.
            # Fixed by (1) re-resolving the connection through the store
            # with `decrypt=True` (the sanctioned way to get a live
            # api_key) and (2) `getattr(..., None)` for the optional field.
            _store = _build_token_webhook_store(cfg)
            _decrypted = (
                _store.get_connection(
                    connection_id=connection.id,
                    org_id=connection.org_id,
                    user_id=connection.user_id,
                    decrypt=True,
                )
                if _store is not None
                else None
            )
            if _decrypted is not None and _decrypted.api_key:
                _fire_and_forget(
                    _register_contact_bg(
                        base_url=connection.base_url,
                        api_key=_decrypted.api_key,
                        session=connection.session_name,
                        sender=sender,
                        push_name=getattr(payload, "pushName", None),
                        org_id=str(intake._org_id),
                    )
                )
        except Exception:
            logger.warning(
                "WhatsApp contact auto-register scheduling failed for sender=%s — continuing",
                sender,
                exc_info=True,
            )

    # ── Bound-chat gate (migration 016) ─────────────────────────────────────────
    # For per-connection routes: if the connection has a non-empty bound_chats
    # list, drop messages from chats not in that list — silently, no reply.
    # The message was already stored to the inbox above (operators can still
    # see it), but the agent takes no action on an unbound chat.
    # This gate fires BEFORE is_authorized so unbound chats never get even the
    # "unauthorized number" reply.
    if connection is not None and not intake.is_chat_bound(payload.chat_id or sender):
        logger.debug(
            "WhatsApp inbound from unbound chat %s (connection=%s) — dropping agent action",
            payload.chat_id or sender,
            connection.id,
        )
        return Response(status_code=status.HTTP_200_OK)

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

    # Process the message.
    # When a per-connection record is present, the auto_reply_enabled toggle
    # gates the chatbot.  Default is OFF — operators can chat manually without
    # the bot interfering.  The legacy global route preserves the old gate
    # (cfg.whatsapp_chatbot_enabled only, no connection context).
    _auto_reply_allowed = (
        connection.auto_reply_enabled if connection is not None
        else True  # legacy route: respect only the settings gate below
    )
    try:
        if cfg.whatsapp_chatbot_enabled and cfg.openai_api_key and _auto_reply_allowed:
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
                    cfg.message_debounce_seconds,
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
                    model=cfg.openai_chat_model,
                    api_key=cfg.openai_api_key,
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


async def _resolve_waha_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Per-request lookup of the WAHA webhook HMAC secret.

    Reads ``waha_webhook_hmac_secret`` at REQUEST time (not
    import time) so test-time settings overrides are honored — the
    import-time-capture trap ``KB § PATTERNS/security/webhook-signatures.md``
    warns about. ``or None`` collapses an empty string to the unset path
    so ``bypass_when_unset=True`` engages below, preserving this router's
    pre-existing dev behavior: no secret configured → accept without
    verification, loudly logged.
    """
    cfg = _cfg_for_request(request)
    return ResolvedSecret(secret=cfg.waha_webhook_hmac_secret or None)


@router.post("/webhook")
# NOTE: `settings` (not `cfg`) is correct here and cannot be changed —
# a decorator is evaluated at IMPORT time, before any request exists
# and before dependency_overrides could apply. The other 14 reads in
# this module now flow through `Depends(get_settings)`.
@limiter.limit(settings.webhook_rate_limit)
async def whatsapp_webhook(
    request: Request,
    cfg=Depends(get_settings),
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_waha_secret,
        scheme="sha256_hex",
        bypass_when_unset=True,
        log_prefix="whatsapp-webhook",
    ),
) -> Response:
    """WAHA webhook endpoint (legacy global route).

    Always returns 200 to prevent WAHA from retrying. Processing
    failures are logged but never surfaced as HTTP errors — WAHA
    doesn't understand them and would just retry indefinitely. The one
    path that DOES return non-200 is a signature mismatch (401, raised
    by ``webhook_endpoint`` before this body ever runs).
    """
    try:
        body = json.loads(verified.body.decode("utf-8")) if verified.body else {}
    except Exception:
        return Response(status_code=status.HTTP_200_OK)

    return await _process_waha_body(body, event_source="webhook", cfg=cfg)


def _build_token_webhook_store(cfg=None):
    """Plain builder — for callers that already hold a settings object.

    Split out of :func:`get_token_webhook_store` so internal call sites
    inside ``_process_waha_body`` can pass the request's resolved ``cfg``
    instead of reaching for the module singleton (the read that forced
    tests to monkeypatch ``settings.encryption_key``).
    """
    cfg = cfg or settings
    try:
        return build_whatsapp_connection_store(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured:
        return None


def get_token_webhook_store(cfg=Depends(get_settings)):
    """DI seam for the token-webhook store (service-role admin client; no JWT).

    Returns ``None`` when encryption isn't configured so the route can 404
    without leaking config state. This is the injectable seam tests override
    (``app.dependency_overrides[get_token_webhook_store]``) — never patch the
    module-level factory (that trips the no-monkey-patch-internals rule and
    stops exercising the real wiring). ``cfg`` flows from the same
    ``get_settings`` seam, so ``override_settings`` reaches it too.
    """
    return _build_token_webhook_store(cfg)


@router.post("/webhook/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def whatsapp_webhook_by_token(
    token: str,
    request: Request,
    cfg=Depends(get_settings),
    store=Depends(get_token_webhook_store),
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_waha_secret,
        scheme="sha256_hex",
        bypass_when_unset=True,
        log_prefix="whatsapp-webhook-token",
    ),
) -> Response:
    """Per-connection token-scoped WAHA webhook endpoint.

    Resolves the connection via the opaque ``token`` path parameter.
    Unknown token → 404 (generic, no token enumeration). Delegates
    to the shared ``_process_waha_body`` pipeline — identical processing
    to the legacy ``/webhook`` route.

    HMAC check uses the same global ``waha_webhook_hmac_secret`` when
    configured (``store`` and ``verified`` are independent ``Depends`` —
    both resolve regardless of order; a signature mismatch still 401s
    before this body runs). No JWT — WAHA calls carry no Authorization
    header.
    """
    # Store is built by the get_token_webhook_store DI seam (service-role admin
    # client; no JWT — this is a public webhook endpoint). It returns None on a
    # config gap (encryption unconfigured) → 404, so we never leak config state
    # to unauthenticated callers. Unknown token → 404. Token lookup is plaintext.
    if store is None:
        logger.warning(
            "whatsapp_webhook_by_token: encryption not configured, cannot resolve token"
        )
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    connection = store.get_by_webhook_token(token)
    if connection is None:
        # Do NOT log the token value — it's a secret routing credential.
        logger.debug("whatsapp_webhook_by_token: unknown token (404)")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    logger.debug(
        "whatsapp_webhook_by_token: resolved connection id=%s session=%s",
        connection.id,
        connection.session_name,
    )

    try:
        body = json.loads(verified.body.decode("utf-8")) if verified.body else {}
    except Exception:
        return Response(status_code=status.HTTP_200_OK)

    return await _process_waha_body(
        body,
        cfg=cfg,
        event_source=f"webhook/{connection.id}",
        connection=connection,
    )


__all__ = ["router"]
