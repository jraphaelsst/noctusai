"""WhatsApp inbox router factory - read + reply on top of the seed
connections organ (``whatsapp_connections_router``).

Routes (all org-scoped; the connection must belong to the caller's org, else
404; no/invalid auth -> 401 from ``get_current_user_org``):

    GET  /api/whatsapp/connections/{id}/chats?q=&limit=&cursor=     -> {items, next_cursor}
    GET  /api/whatsapp/connections/{id}/chats/{chat_id}/messages?before=&limit= -> {items, has_more}
    POST /api/whatsapp/connections/{id}/chats/{chat_id}/messages {text}         -> InboxMessage (201)
    POST /api/whatsapp/connections/{id}/chats/{chat_id}/read                    -> 204
    POST /api/whatsapp/connections/{id}/backfill                                -> 202
    GET  /api/whatsapp/connections/{id}/events                                  (SSE)
    POST {webhook_path_prefix}/{token}                                          (PUBLIC inbound webhook)

**The webhook path is the URL the connections router mints.**
``create_whatsapp_connections_router`` registers
``{resolve_webhook_base_url()}{webhook_path_prefix}/{token}`` on WAHA with
``webhook_path_prefix="/api/whatsapp/webhook"`` by default; this factory takes
the same ``webhook_path_prefix`` default, and a product that overrides one MUST
pass the same value to both (the round trip is a test:
``test_webhook_path_matches_minted_url``).

Messages page: ``items`` are chronological (oldest -> newest) inside the page,
the page being the newest ``limit`` messages older than ``before``;
``before`` is the opaque ``<iso>|<id>`` of the OLDEST message the client holds
(the FE hook builds it) - a bare ISO timestamp is accepted too. Chats paginate
newest-activity-first with the opaque ``next_cursor``.

Security notes:

* The webhook is public by design (WAHA cannot send a JWT). Its credential is
  the unguessable per-connection token in the path (unknown token -> generic
  404, never logged) PLUS an HMAC (``X-Webhook-Hmac-SHA256``) when
  ``webhook_hmac_secret`` is set. ``set_webhook`` in the seed client registers
  ``hmac: None`` per webhook, so signing only happens if WAHA itself is run
  with a global ``WHATSAPP_HOOK_HMAC_KEY`` - set the same value here.
* Sending never falls back to the Fake: a connection with no ``base_url``
  yields 503 instead of a fake "Sent".
* Outbound pacing is the seed ``whatsapp`` token bucket that every
  ``WahaClient`` request already goes through (``integrations.rate_limit``).
* ``mirror_read_to_whatsapp`` (default OFF) additionally sends WAHA
  ``sendSeen`` on mark-read - blue ticks on the owner's real phone.

Decoupling: imports nothing from ``app.*``; every product concern is a kwarg
(Class-B DI seam).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Optional
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    WhatsAppConnectionStoreError,
    get_whatsapp_client,
)
from noctusai_lib.integrations.whatsapp.connection_store import resolve_by_webhook_token
from noctusai_lib.integrations.whatsapp.inbox import (
    EVENT_CHAT_READ,
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_NEW,
    InboxMessage,
    InboxRealtime,
    OnNewChat,
    WhatsAppChatStore,
    backfill_connection,
    ingest_waha_event,
    inbox_scope,
    is_backfill_running,
)
from noctusai_lib.integrations.whatsapp.inbox.store import utc_now_iso
from noctusai_lib.integrations.whatsapp.lid_auth import (
    LidPhoneCache,
    extract_resolved_remote,
    remember_lid_phone,
)
from noctusai_lib.integrations.whatsapp.mappers import normalize_waha_id
from noctusai_lib.realtime import create_sse_router
from noctusai_lib.security.api_keys import EncryptionNotConfigured
from noctusai_lib.security.webhook_signatures import static_secret_resolver, webhook_endpoint

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4096


class InboxChatOut(StrictHttpModel):
    chat_id: str
    name: str
    phone: Optional[str] = None
    is_group: bool
    last_message_preview: str
    last_message_at: Optional[str] = None
    last_message_from_me: Optional[bool] = None
    unread_count: int


class InboxChatsPageOut(StrictHttpModel):
    items: list[InboxChatOut]
    next_cursor: Optional[str] = None


class InboxMessageOut(StrictHttpModel):
    id: str
    chat_id: str
    from_me: bool
    body: str
    type: str
    media_url: Optional[str] = None
    ack: Optional[int] = None
    timestamp: str
    sender_name: Optional[str] = None


class InboxMessagesPageOut(StrictHttpModel):
    items: list[InboxMessageOut]
    has_more: bool


class SendInboxMessageIn(StrictHttpModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class BackfillStartedOut(StrictHttpModel):
    status: str  # started | already_running


def _default_resolve_org_id(raw: Any) -> UUID:
    return UUID(str(raw))


def create_whatsapp_inbox_router(
    *,
    chat_store_factory: Callable[[], WhatsAppChatStore],
    connection_store_factory: Callable[[], WhatsAppConnectionStore],
    get_current_user_org: Callable[..., Any],
    waha_client_factory: Callable[..., Any] = get_whatsapp_client,
    on_new_chat: Optional[OnNewChat] = None,
    realtime: Optional[InboxRealtime] = None,
    lid_cache: Optional[LidPhoneCache] = None,
    webhook_hmac_secret: Optional[str] = None,
    webhook_path_prefix: str = "/api/whatsapp/webhook",
    prefix: str = "/api/whatsapp/connections",
    resolve_org_id: Callable[[Any], UUID] = _default_resolve_org_id,
    mirror_read_to_whatsapp: bool = False,
    backfill_kwargs: Optional[dict[str, Any]] = None,
) -> APIRouter:
    """Build the inbox router (authenticated routes + the public webhook)."""
    router = APIRouter(tags=["WhatsApp Inbox"])
    backfill_kwargs = dict(backfill_kwargs or {})

    # ─── dependencies / helpers ─────────────────────────────────────────
    def _conn_store() -> WhatsAppConnectionStore:
        try:
            return connection_store_factory()
        except EncryptionNotConfigured as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    def _require_record(
        store: WhatsAppConnectionStore, *, connection_id: UUID, org_id: UUID, decrypt: bool = False
    ) -> WhatsAppConnectionRecord:
        try:
            record = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=decrypt)
        except WhatsAppConnectionStoreError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connection not found")
        return record

    def _waha_client(record: WhatsAppConnectionRecord) -> Any:
        if not record.base_url:
            # get_whatsapp_client(base_url=None) would hand back the FAKE client
            # and report a send that never happened.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, detail="connection has no WAHA base_url configured"
            )
        return waha_client_factory(
            base_url=record.base_url, api_key=record.api_key, session=record.session_name
        )

    def _chat_store() -> WhatsAppChatStore:
        return chat_store_factory()

    # ─── reads ──────────────────────────────────────────────────────────
    @router.get(f"{prefix}/{{connection_id}}/chats", response_model=InboxChatsPageOut)
    def list_chats(
        connection_id: UUID,
        q: Optional[str] = Query(default=None, max_length=100),
        limit: int = Query(default=30, ge=1, le=200),
        cursor: Optional[str] = Query(default=None),
        auth: tuple = Depends(get_current_user_org),
        conn_store: WhatsAppConnectionStore = Depends(_conn_store),
        chats: WhatsAppChatStore = Depends(_chat_store),
    ) -> InboxChatsPageOut:
        org_id = resolve_org_id(auth[2])
        _require_record(conn_store, connection_id=connection_id, org_id=org_id)
        try:
            items, next_cursor = chats.list_chats(
                org_id=org_id, connection_id=connection_id, q=q, limit=limit, cursor=cursor
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        return InboxChatsPageOut(items=[InboxChatOut(**c.as_dict()) for c in items], next_cursor=next_cursor)

    @router.get(f"{prefix}/{{connection_id}}/chats/{{chat_id:path}}/messages", response_model=InboxMessagesPageOut)
    def list_messages(
        connection_id: UUID,
        chat_id: str,
        before: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        auth: tuple = Depends(get_current_user_org),
        conn_store: WhatsAppConnectionStore = Depends(_conn_store),
        chats: WhatsAppChatStore = Depends(_chat_store),
    ) -> InboxMessagesPageOut:
        org_id = resolve_org_id(auth[2])
        _require_record(conn_store, connection_id=connection_id, org_id=org_id)
        try:
            items, has_more = chats.list_messages(
                org_id=org_id, connection_id=connection_id, chat_id=chat_id, before=before, limit=limit
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        return InboxMessagesPageOut(
            items=[InboxMessageOut(**m.as_dict()) for m in items], has_more=has_more
        )

    # ─── send ───────────────────────────────────────────────────────────
    @router.post(
        f"{prefix}/{{connection_id}}/chats/{{chat_id:path}}/messages",
        response_model=InboxMessageOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def send_message(
        connection_id: UUID,
        chat_id: str,
        body: SendInboxMessageIn,
        auth: tuple = Depends(get_current_user_org),
        conn_store: WhatsAppConnectionStore = Depends(_conn_store),
        chats: WhatsAppChatStore = Depends(_chat_store),
    ) -> InboxMessageOut:
        org_id = resolve_org_id(auth[2])
        record = await run_in_threadpool(
            lambda: _require_record(conn_store, connection_id=connection_id, org_id=org_id, decrypt=True)
        )
        chat = await run_in_threadpool(
            lambda: chats.get_chat(org_id=org_id, connection_id=connection_id, chat_id=chat_id)
        )
        if chat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chat not found")
        client = _waha_client(record)
        try:
            response = await client.send_text(chat_id, body.text)
        except WahaSessionNotReady as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="WhatsApp session is not ready") from exc
        except Exception as exc:  # noqa: BLE001 - WAHA/transport failure, nothing was persisted
            logger.warning("inbox send failed connection=%s: %s", connection_id, type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="WAHA send failed") from exc

        response = response if isinstance(response, dict) else {}
        message_id = normalize_waha_id(response.get("id"))
        if not message_id:
            # WAHA always returns an id; if it did not, keep the message visible
            # under a synthetic id (the echo would duplicate it - logged, rare).
            message_id = f"local-{uuid.uuid4()}"
            logger.warning("inbox send: WAHA returned no message id (connection=%s)", connection_id)
        if lid_cache is not None:
            remember_lid_phone(
                lid_cache, lid_chat_id=chat_id, resolved_remote=extract_resolved_remote(response)
            )
        message = InboxMessage(
            id=message_id, chat_id=chat_id, from_me=True, body=body.text, type="chat", media_url=None,
            ack=_ack_of(response), timestamp=utc_now_iso(), sender_name=None,
        )

        def _persist() -> Any:
            chats.insert_message(org_id=org_id, connection_id=connection_id, message=message)
            return chats.refresh_chat_after_message(
                org_id=org_id, connection_id=connection_id, chat_id=chat_id, message=message
            )

        fresh_chat = await run_in_threadpool(_persist)
        if realtime is not None:
            await realtime.publish(connection_id, EVENT_MESSAGE_NEW, {"chat_id": chat_id, "message": message.as_dict()})
            await realtime.publish(connection_id, EVENT_CHAT_UPSERT, {"chat": fresh_chat.as_dict()})
        return InboxMessageOut(**message.as_dict())

    # ─── read ───────────────────────────────────────────────────────────
    @router.post(f"{prefix}/{{connection_id}}/chats/{{chat_id:path}}/read", status_code=status.HTTP_204_NO_CONTENT)
    async def mark_read(
        connection_id: UUID,
        chat_id: str,
        background: BackgroundTasks,
        auth: tuple = Depends(get_current_user_org),
        conn_store: WhatsAppConnectionStore = Depends(_conn_store),
        chats: WhatsAppChatStore = Depends(_chat_store),
    ) -> Response:
        org_id = resolve_org_id(auth[2])
        record = await run_in_threadpool(
            lambda: _require_record(
                conn_store, connection_id=connection_id, org_id=org_id, decrypt=mirror_read_to_whatsapp
            )
        )
        chat = await run_in_threadpool(
            lambda: chats.mark_read(org_id=org_id, connection_id=connection_id, chat_id=chat_id)
        )
        if chat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chat not found")
        if realtime is not None:
            await realtime.publish(
                connection_id, EVENT_CHAT_READ, {"chat_id": chat_id, "unread_count": 0}
            )
        if mirror_read_to_whatsapp:
            background.add_task(_send_seen, _waha_client(record), chat_id, connection_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── backfill ───────────────────────────────────────────────────────
    @router.post(
        f"{prefix}/{{connection_id}}/backfill",
        response_model=BackfillStartedOut,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_backfill(
        connection_id: UUID,
        background: BackgroundTasks,
        auth: tuple = Depends(get_current_user_org),
        conn_store: WhatsAppConnectionStore = Depends(_conn_store),
        chats: WhatsAppChatStore = Depends(_chat_store),
    ) -> BackfillStartedOut:
        org_id = resolve_org_id(auth[2])
        record = await run_in_threadpool(
            lambda: _require_record(conn_store, connection_id=connection_id, org_id=org_id, decrypt=True)
        )
        if is_backfill_running(connection_id):
            return BackfillStartedOut(status="already_running")
        client = _waha_client(record)

        async def _run() -> None:
            report = await backfill_connection(
                record=record, chat_store=chats, waha_client=client, lid_cache=lid_cache, **backfill_kwargs
            )
            logger.info(
                "inbox backfill connection=%s status=%s chats=%d messages=%d",
                connection_id, report.status, report.chats_synced, report.messages_inserted,
            )

        background.add_task(_run)
        return BackfillStartedOut(status="started")

    # ─── SSE ────────────────────────────────────────────────────────────
    if realtime is not None:
        async def _scope(request: Request, auth_ctx: Any) -> str:
            connection_id = UUID(str(request.path_params["connection_id"]))
            org_id = resolve_org_id(auth_ctx[2])
            await run_in_threadpool(
                lambda: _require_record(_conn_store(), connection_id=connection_id, org_id=org_id)
            )
            return inbox_scope(connection_id)

        router.include_router(
            create_sse_router(
                realtime.bus, scope_resolver=_scope, auth_dependency=get_current_user_org,
                path=f"{prefix}/{{connection_id}}/events",
            )
        )

    # ─── PUBLIC inbound webhook ─────────────────────────────────────────
    @router.post(f"{webhook_path_prefix}/{{token}}")
    async def inbound_webhook(
        token: str,
        verified: Any = webhook_endpoint(
            secret_resolver=static_secret_resolver(webhook_hmac_secret),
            scheme="sha256_hex",
            bypass_when_unset=True,
            log_prefix="whatsapp-inbox-webhook",
        ),
    ) -> dict[str, str]:
        try:
            store = connection_store_factory()
        except EncryptionNotConfigured:
            raise HTTPException(status.HTTP_404_NOT_FOUND) from None  # never leak config state
        record = await run_in_threadpool(lambda: resolve_by_webhook_token(store, token))
        if record is None:
            # The token is a routing credential: never logged, generic 404.
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        try:
            body = json.loads(verified.body.decode("utf-8")) if verified.body else {}
        except ValueError:
            return {"status": "ignored"}
        if not isinstance(body, dict):
            return {"status": "ignored"}
        result = await ingest_waha_event(
            body,
            connection=record,
            chat_store=chat_store_factory(),
            realtime=realtime,
            on_new_chat=on_new_chat,
            lid_cache=lid_cache,
            waha_client_factory=lambda rec: _client_for_identity(rec, store),
        )
        return {"status": result.status}

    def _client_for_identity(rec: WhatsAppConnectionRecord, store: WhatsAppConnectionStore) -> Any:
        """WAHA client for @lid resolution (needs the decrypted key; the
        token-resolved record is not decrypted)."""
        full = store.get_connection(connection_id=rec.id, org_id=rec.org_id, decrypt=True)
        if full is None or not full.base_url:
            return None
        return waha_client_factory(base_url=full.base_url, api_key=full.api_key, session=full.session_name)

    return router


def _ack_of(response: dict[str, Any]) -> int:
    try:
        return int(response.get("ack"))
    except (TypeError, ValueError):
        return 0


async def _send_seen(client: Any, chat_id: str, connection_id: UUID) -> None:
    try:
        await client.send_seen(chat_id)
    except Exception as exc:  # noqa: BLE001 - best-effort mirror; the badge is already cleared
        logger.warning("send_seen failed connection=%s: %s", connection_id, type(exc).__name__)
