"""WAHA webhook event -> inbox state: parse, resolve identity, persist,
publish, and fire ``on_new_chat`` exactly once per new non-group chat.

Events: ``message`` / ``message.any`` (both persisted; ``message.any`` also
carries the echo of our own sends and of messages typed on the phone),
``message.ack`` (delivery/read receipts), ``session.status`` (published for
the UI), anything else ignored.

Failure model (deliberate): a payload we cannot make sense of is IGNORED with
a 200 (retrying garbage helps nobody); an infrastructure failure
(store down) PROPAGATES so the router answers 5xx and WAHA retries - the
``UNIQUE (connection_id, waha_message_id)`` guard makes the retry idempotent.
A failing ``on_new_chat`` consumer never fails the webhook: the claim is
released and the next inbound message of that chat retries it.

``on_new_chat`` contract: exactly once per chat row that an INBOUND message
created, non-group, per (connection, chat). The decision is an atomic claim
on the chat row (``claim_new_chat_notification``), so a replayed webhook, a
``message`` + ``message.any`` pair, or deleting the downstream lead (the chat
row persists) can never fire it again. Chats created by an outbound message
or by backfill never fire it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from noctusai_lib.integrations.whatsapp.connection_store import WhatsAppConnectionRecord
from noctusai_lib.integrations.whatsapp.identity import resolve_identity
from noctusai_lib.integrations.whatsapp.inbox.realtime import (
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
    InboxRealtime,
)
from noctusai_lib.integrations.whatsapp.inbox.store import WhatsAppChatStore
from noctusai_lib.integrations.whatsapp.inbox.types import (
    ORIGIN_INBOUND,
    ORIGIN_OUTBOUND,
    InboxChat,
    InboxMessage,
    e164,
)
from noctusai_lib.integrations.whatsapp.lid_auth import LidPhoneCache, is_lid, normalize_phone
from noctusai_lib.integrations.whatsapp.mappers import (
    extract_from_name,
    extract_media,
    first_text,
    normalize_waha_id,
)

logger = logging.getLogger(__name__)

OnNewChat = Callable[[UUID, UUID, InboxChat], Awaitable[None]]
#: ``on_message(org_id, connection_id, chat, message)`` - fired for every message that was NEWLY stored (inbound
#: and outbound, never for a duplicate or a backfilled one). Best-effort: a raising consumer is logged and
#: never fails the webhook (e.g. keep a downstream card's last-message preview fresh).
OnMessage = Callable[[UUID, UUID, InboxChat, InboxMessage], Awaitable[None]]
#: ``record -> WAHA client`` (only used to resolve an unknown @lid to a phone).
WahaClientFactory = Callable[[WhatsAppConnectionRecord], Any]

_IGNORED_SUFFIXES = ("@broadcast", "@newsletter")
_PHONE_SUFFIXES = ("@c.us", "@s.whatsapp.net")


@dataclass(frozen=True)
class IngestResult:
    status: str  # message | duplicate | ack | session | ignored
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    new_chat_fired: bool = False


@dataclass(frozen=True)
class ParsedMessage:
    message: InboxMessage  # chat_id is the RAW WAHA chat jid until identity resolution
    chat_jid: str
    group_name: Optional[str] = None


@dataclass(frozen=True)
class ChatIdentity:
    chat_id: str
    phone: Optional[str]  # E.164
    name: Optional[str]
    is_group: bool


# ─── parsing ────────────────────────────────────────────────────────────────


def epoch_to_iso(value: Any) -> str:
    """WAHA timestamps are epoch SECONDS (some builds emit ms). Falls back to
    now so a malformed timestamp never drops a message."""
    try:
        number = float(value)
        if number > 1e11:  # milliseconds
            number /= 1000.0
        if number > 0:
            return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return datetime.now(timezone.utc).isoformat()


def _message_type(payload: dict[str, Any], mimetype: Optional[str], has_media: bool) -> str:
    explicit = payload.get("type")
    if not isinstance(explicit, str) or not explicit.strip():
        data = payload.get("_data")
        explicit = data.get("type") if isinstance(data, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    if has_media and mimetype:
        family = mimetype.split("/", 1)[0].lower()
        if family in {"image", "video", "audio"}:
            return family
        return "document"
    return "media" if has_media else "chat"


def parse_waha_message(
    payload: dict[str, Any], *, chat_jid: Optional[str] = None
) -> Optional[ParsedMessage]:
    """One WAHA message object (webhook payload OR history item) -> a
    :class:`ParsedMessage`, or ``None`` when it is not a user-visible message
    (no id, no chat, system/protocol stubs with neither text nor media).

    The chat is the jid the conversation lives on - ``to`` for our own
    messages, ``from`` for inbound (``participant`` is the group SENDER, never
    the chat). It is never rebuilt from a sender field.
    """
    message_id = normalize_waha_id(payload.get("id"))
    if not message_id:
        return None
    from_me = bool(payload.get("fromMe"))
    jid = chat_jid or first_text(payload, "chatId") or first_text(payload, "to" if from_me else "from")
    if not jid or jid.endswith(_IGNORED_SUFFIXES) or jid == "status@broadcast":
        return None
    body = payload.get("body")
    body = body if isinstance(body, str) else ""
    media = extract_media(payload)
    has_media = bool(payload.get("hasMedia"))
    if not body.strip() and not has_media:
        return None
    is_group = jid.endswith("@g.us")
    author = first_text(payload, "participant", "author") if is_group else ""
    sender_phone = e164(normalize_phone(author)) if author and not is_lid(author) else (
        e164(normalize_phone(jid)) if jid.endswith(_PHONE_SUFFIXES) else None
    )
    message = InboxMessage(
        id=message_id,
        chat_id=jid,
        from_me=from_me,
        body=body,
        type=_message_type(payload, media.mimetype if media else None, has_media),
        media_url=media.url if media else None,
        ack=_int_or_none(payload.get("ack")),
        timestamp=epoch_to_iso(payload.get("timestamp")),
        sender_name=None if from_me else extract_from_name(payload),
        media_mimetype=media.mimetype if media else None,
        sender_phone=sender_phone,
    )
    return ParsedMessage(message=message, chat_jid=jid)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ─── identity ───────────────────────────────────────────────────────────────


async def resolve_chat_identity(
    chat_jid: str,
    *,
    push_name: Optional[str],
    lid_cache: Optional[LidPhoneCache],
    waha_client: Any = None,
) -> ChatIdentity:
    """Canonical chat id + display data for a raw WAHA chat jid.

    * group -> kept as is (no phone);
    * ``@c.us`` / ``@s.whatsapp.net`` -> ``<digits>@c.us`` (ONE key per human);
    * ``@lid`` -> the seed's lid<->phone cache first, then (fail-soft)
      ``resolve_identity`` over WAHA; resolved -> the phone chat id, else the
      opaque ``@lid`` is kept (phone ``None``) rather than guessed.
    """
    if chat_jid.endswith("@g.us"):
        return ChatIdentity(chat_jid, None, None, True)
    if is_lid(chat_jid):
        phone = lid_cache.get_phone_for_lid(chat_jid) if lid_cache is not None else None
        name = push_name
        if not phone and waha_client is not None:
            identity = await resolve_identity(waha_client, chat_jid)
            phone, name = identity.phone, name or identity.name
            if phone and lid_cache is not None:
                lid_cache.bind(chat_jid, phone)
        if phone:
            return ChatIdentity(f"{phone}@c.us", e164(phone), name, False)
        return ChatIdentity(chat_jid, None, name, False)
    digits = normalize_phone(chat_jid)
    chat_id = f"{digits}@c.us" if chat_jid.endswith(_PHONE_SUFFIXES) and digits else chat_jid
    return ChatIdentity(chat_id, e164(digits) if chat_jid.endswith(_PHONE_SUFFIXES) else None, push_name, False)


# ─── the pipeline ───────────────────────────────────────────────────────────


async def _io(fn: Callable[..., Any], /, **kwargs: Any) -> Any:
    """Store calls are blocking (Supabase over HTTP): keep the event loop free."""
    return await run_in_threadpool(fn, **kwargs)


async def persist_message(
    *,
    parsed: ParsedMessage,
    org_id: UUID,
    connection_id: UUID,
    chat_store: WhatsAppChatStore,
    identity: ChatIdentity,
    origin: str,
) -> tuple[bool, InboxChat, Any]:
    """ensure chat -> insert message (dedup) -> refresh chat. Returns
    ``(inserted, chat, ChatState)``. Shared by live ingest and backfill."""
    message = replace(parsed.message, chat_id=identity.chat_id)
    state = await _io(
        chat_store.ensure_chat, org_id=org_id, connection_id=connection_id, chat_id=identity.chat_id,
        name=identity.name, phone=identity.phone, is_group=identity.is_group, origin=origin,
    )
    inserted = await _io(chat_store.insert_message, org_id=org_id, connection_id=connection_id, message=message)
    chat = await _io(
        chat_store.refresh_chat_after_message, org_id=org_id, connection_id=connection_id,
        chat_id=identity.chat_id, message=message, name=identity.name, phone=identity.phone,
    )
    return inserted, chat, state


async def ingest_waha_event(
    body: dict[str, Any],
    *,
    connection: WhatsAppConnectionRecord,
    chat_store: WhatsAppChatStore,
    realtime: Optional[InboxRealtime] = None,
    on_new_chat: Optional[OnNewChat] = None,
    on_message: Optional[OnMessage] = None,
    lid_cache: Optional[LidPhoneCache] = None,
    waha_client_factory: Optional[WahaClientFactory] = None,
) -> IngestResult:
    event = str(body.get("event") or "")
    payload = body.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    org_id, connection_id = connection.org_id, connection.id

    if event == "session.status":
        status = payload.get("status") or body.get("status")
        if realtime is not None and status:
            await realtime.publish(connection_id, EVENT_SESSION_STATUS, {"status": str(status)})
        return IngestResult("session")

    if event == "message.ack":
        waha_id = normalize_waha_id(payload.get("id"))
        ack = _int_or_none(payload.get("ack"))
        if not waha_id or ack is None:
            return IngestResult("ignored")
        updated = await _io(
            chat_store.apply_ack, org_id=org_id, connection_id=connection_id,
            waha_message_id=waha_id, ack=ack,
        )
        if updated is None:  # ack before our insert / a message we never stored
            return IngestResult("ignored")
        if realtime is not None:
            await realtime.publish(
                connection_id, EVENT_MESSAGE_ACK,
                {"chat_id": updated.chat_id, "id": updated.id, "ack": updated.ack},
            )
        return IngestResult("ack", chat_id=updated.chat_id, message_id=updated.id)

    if event not in {"message", "message.any"}:
        return IngestResult("ignored")

    parsed = parse_waha_message(payload)
    if parsed is None:
        return IngestResult("ignored")

    waha_client = None
    if is_lid(parsed.chat_jid) and waha_client_factory is not None:
        waha_client = waha_client_factory(connection)
    identity = await resolve_chat_identity(
        parsed.chat_jid, push_name=parsed.message.sender_name if not parsed.message.from_me else None,
        lid_cache=lid_cache, waha_client=waha_client,
    )
    origin = ORIGIN_OUTBOUND if parsed.message.from_me else ORIGIN_INBOUND
    inserted, chat, state = await persist_message(
        parsed=parsed, org_id=org_id, connection_id=connection_id, chat_store=chat_store,
        identity=identity, origin=origin,
    )

    if inserted and realtime is not None:
        stored = replace(parsed.message, chat_id=identity.chat_id)
        await realtime.publish(
            connection_id, EVENT_MESSAGE_NEW, {"chat_id": identity.chat_id, "message": stored.as_dict()}
        )
        await realtime.publish(connection_id, EVENT_CHAT_UPSERT, {"chat": chat.as_dict()})

    if inserted and on_message is not None:
        await notify_message(on_message, org_id, connection_id, chat, replace(parsed.message, chat_id=identity.chat_id))

    fired = False
    if on_new_chat is not None and state.notification_pending:
        fired = await _fire_new_chat(
            chat_store=chat_store, org_id=org_id, connection_id=connection_id, chat=chat,
            on_new_chat=on_new_chat,
        )
    return IngestResult(
        "message" if inserted else "duplicate", chat_id=identity.chat_id,
        message_id=parsed.message.id, new_chat_fired=fired,
    )


async def notify_message(
    on_message: OnMessage, org_id: UUID, connection_id: UUID, chat: InboxChat, message: InboxMessage
) -> None:
    """Run the best-effort ``on_message`` seam (shared by live ingest and the router's send path)."""
    try:
        await on_message(org_id, connection_id, chat, message)
    except Exception:  # noqa: BLE001 - a consumer bug must not fail the webhook / the send
        logger.exception(
            "on_message failed (connection=%s chat=%s message=%s)", connection_id, chat.chat_id, message.id
        )


async def _fire_new_chat(
    *, chat_store: WhatsAppChatStore, org_id: UUID, connection_id: UUID, chat: InboxChat,
    on_new_chat: OnNewChat,
) -> bool:
    won = await _io(
        chat_store.claim_new_chat_notification, org_id=org_id, connection_id=connection_id,
        chat_id=chat.chat_id,
    )
    if not won:
        return False
    try:
        await on_new_chat(org_id, connection_id, chat)
    except Exception:  # noqa: BLE001 - a consumer bug must not fail the webhook
        logger.exception(
            "on_new_chat failed (connection=%s chat=%s) - claim released, the next inbound "
            "message of this chat retries", connection_id, chat.chat_id,
        )
        await _io(
            chat_store.release_new_chat_notification, org_id=org_id, connection_id=connection_id,
            chat_id=chat.chat_id,
        )
        return False
    return True
