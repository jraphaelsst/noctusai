"""WhatsApp inbox router factory - read + reply on top of the seed
connections organ (``whatsapp_connections_router``).

Routes (all org-scoped; the connection must belong to the caller's org, else
404; no/invalid auth -> 401 from ``get_current_user_org``):

    GET  /api/whatsapp/connections/{id}/chats?q=&limit=&cursor=     -> {items, next_cursor}
    GET  /api/whatsapp/connections/{id}/chats/{chat_id}/messages?before=&limit= -> {items, has_more}
    POST /api/whatsapp/connections/{id}/chats/{chat_id}/messages {text}         -> InboxMessage (201)
    POST /api/whatsapp/connections/{id}/chats/{chat_id}/read                    -> 204
    POST /api/whatsapp/connections/{id}/backfill                                -> 202
    PATCH /api/whatsapp/connections/{id}/chats/{chat_id}/agent-paused {paused}  -> InboxChat   (only with on_agent_pause)
    POST /api/whatsapp/connections/{id}/chats/{chat_id}/apagar-dados            -> {messages_deleted, chat_deleted}
                                                                                   (only with allow_chat_delete)
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
  404, never logged) PLUS an HMAC (WAHA's ``X-Webhook-Hmac`` + ``X-Webhook-Hmac-Algorithm``, sha512 default) when
  ``webhook_hmac_secret`` is set. ``set_webhook`` in the seed client registers
  ``hmac: None`` per webhook, so signing only happens if WAHA itself is run
  with a global ``WHATSAPP_HOOK_HMAC_KEY`` (or the session's ``hmac.key``) - set the same value here.
* **Per-app switch**: a connection with ``app_enabled=False`` answers the webhook ``200 {"status":"disabled"}``
  (nothing stored, no ``on_new_chat`` / ``on_message``) and refuses sends with 409 ``app_disabled``. A
  ``session_role='borrower'`` line cannot backfill (409 ``session_borrowed``).
* **Per-chat agent pause** (``on_agent_pause`` given): ``PATCH .../agent-paused`` records ``agent_paused`` on the
  chat AFTER the product's ``on_agent_pause(org_id, connection_id, chat, paused, actor)`` hook accepted it (a
  raising hook -> 502 and nothing recorded, so the flag never claims a pause the product did not apply). The
  organ attaches no meaning to the flag - what pausing DOES is the product's. Pushed to every client as a
  ``chat.upsert``.
* **Per-chat LGPD erasure** (``allow_chat_delete=True``): ``POST .../apagar-dados`` runs the optional
  ``on_delete_chat(org_id, connection_id, chat_id, actor)`` downstream cleanup FIRST (a raising hook -> 502, nothing
  erased, so the call is retriable), then deletes the chat + its messages, pushes ``chat.deleted`` and writes ONE
  audit row with NO content: who, when, which line and a hash of the chat id - never the number or a message.
  Both routes use ``get_admin_user_org`` (default: ``get_current_user_org``) - pass an admin dependency.
* Sending never falls back to the Fake: a connection with no ``base_url``
  yields 503 instead of a fake "Sent".
* Outbound pacing is the seed ``whatsapp`` token bucket that every
  ``WahaClient`` request already goes through (``integrations.rate_limit``).
* ``mirror_read_to_whatsapp`` (default OFF) additionally sends WAHA
  ``sendSeen`` on mark-read - blue ticks on the owner's real phone.

``on_message(org_id, connection_id, chat, message)`` (optional) fires for every newly stored message - inbound
webhook AND outbound send from this router; best-effort (a raising consumer is logged, never fails the call).

``should_store(message, chat) -> True | False | "<reason>"`` (optional) is the PRE-STORE predicate seam: it runs
before anything is persisted/published/notified (default: store all). A shadow line passes
``inbound_one_to_one_only(...)``; a skipped message answers ``200 {"status": "skipped"}``.

Decoupling: imports nothing from ``app.*``; every product concern is a kwarg
(Class-B DI seam).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional, Union
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.audit.types import AuditActor, AuditEntry
from noctusai_lib.api.integration_errors import integration_error
from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    WhatsAppConnectionStoreError,
    get_whatsapp_client,
)
from noctusai_lib.integrations.whatsapp.connection_store import resolve_by_webhook_token
from noctusai_lib.integrations.whatsapp.inbox import (
    EVENT_CHAT_DELETED,
    EVENT_CHAT_READ,
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_NEW,
    InboxChat,
    InboxMessage,
    InboxRealtime,
    OnMessage,
    OnNewChat,
    WhatsAppChatStore,
    backfill_connection,
    ShouldStore,
    ingest_waha_event,
    inbox_scope,
    is_backfill_running,
    notify_message,
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
    agent_paused: bool = False


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


class AgentPausedIn(StrictHttpModel):
    paused: bool


class ChatDeletedOut(StrictHttpModel):
    messages_deleted: int
    chat_deleted: bool


#: ``on_agent_pause(org_id, connection_id, chat, paused, actor)`` - the product applies the pause (sync or async).
OnAgentPause = Callable[[UUID, UUID, InboxChat, bool, Optional[str]], Union[None, Awaitable[None]]]
#: ``on_delete_chat(org_id, connection_id, chat_id, actor)`` - downstream cleanup before the erase (sync or async).
OnDeleteChat = Callable[[UUID, UUID, str, Optional[str]], Union[None, Awaitable[None]]]


def _default_resolve_org_id(raw: Any) -> UUID:
    return UUID(str(raw))


#: The routes ``read_only=True`` leaves UNMOUNTED, as (HTTP method, path template relative to the router ``prefix``).
#: An explicit list, not a function-name filter: a test pins it, and a new write route must be added HERE to be covered.
READ_ONLY_UNMOUNTED_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/{connection_id}/chats/{chat_id:path}/messages"),  # send
    ("POST", "/{connection_id}/backfill"),                      # history backfill (a read of WAHA, but a bulk one)
    ("PATCH", "/{connection_id}/chats/{chat_id:path}/agent-paused"),  # product hook + a store write
    ("POST", "/{connection_id}/chats/{chat_id:path}/apagar-dados"),   # per-chat erasure
)


def create_whatsapp_inbox_router(
    *,
    chat_store_factory: Callable[[], WhatsAppChatStore],
    connection_store_factory: Callable[[], WhatsAppConnectionStore],
    get_current_user_org: Callable[..., Any],
    waha_client_factory: Callable[..., Any] = get_whatsapp_client,
    on_new_chat: Optional[OnNewChat] = None,
    on_message: Optional[OnMessage] = None,
    realtime: Optional[InboxRealtime] = None,
    lid_cache: Optional[LidPhoneCache] = None,
    webhook_hmac_secret: Optional[str] = None,
    webhook_path_prefix: str = "/api/whatsapp/webhook",
    prefix: str = "/api/whatsapp/connections",
    resolve_org_id: Callable[[Any], UUID] = _default_resolve_org_id,
    mirror_read_to_whatsapp: bool = False,
    backfill_kwargs: Optional[dict[str, Any]] = None,
    should_store: Optional[ShouldStore] = None,
    read_only: bool = False,
    webhook_only: bool = False,
    require_webhook_hmac: bool = False,
    on_session_status: Optional[Callable[[WhatsAppConnectionRecord, str], Any]] = None,
    on_agent_pause: Optional[OnAgentPause] = None,
    on_delete_chat: Optional[OnDeleteChat] = None,
    allow_chat_delete: bool = False,
    get_admin_user_org: Optional[Callable[..., Any]] = None,
    audit_product_slug: str = "",
) -> APIRouter:
    """Build the inbox router (authenticated routes + the public webhook).

    ``read_only=True`` (a shadow line): the send and backfill routes are NOT MOUNTED (construction layer of the
    zero-write defence, KB § whatsapp.md § 6a) and the read mirror to WhatsApp is forced off; mark-read stays local.

    ``webhook_only=True`` mounts NOTHING but the public inbound webhook (no chats/messages reads, no mark-read, no
    send, no backfill, no SSE): a line whose stored traffic is consumed only through the ``on_message`` seam (the
    Assistant). ``require_webhook_hmac=True`` makes the HMAC mandatory: no secret => the webhook answers 401 to
    everything, and building the router in a deploy without a secret raises ``WebhookHmacRequired`` (refuse to boot).
    ``on_session_status(record, status)`` (sync or async, best-effort) fires on each WAHA ``session.status`` event.

    ``on_agent_pause`` mounts the per-chat agent-pause route; ``allow_chat_delete=True`` (optionally with
    ``on_delete_chat``) mounts the per-chat erasure route. Both default OFF (a consumer that passes neither has the
    exact route surface it had before). ``get_admin_user_org`` is their auth dependency (default
    ``get_current_user_org``); ``audit_product_slug`` labels the erasure audit row.
    """
    if require_webhook_hmac and not webhook_hmac_secret and is_deploy_context():
        raise WebhookHmacRequired(
            "the WhatsApp webhook HMAC secret is required here (require_webhook_hmac=True) and none is set"
        )
    if read_only:
        mirror_read_to_whatsapp = False
    router = APIRouter(tags=["WhatsApp Inbox"])
    backfill_kwargs = dict(backfill_kwargs or {})

    # ─── dependencies / helpers ─────────────────────────────────────────
    def _conn_store() -> WhatsAppConnectionStore:
        try:
            return connection_store_factory()
        except EncryptionNotConfigured as exc:
            raise integration_error("not_configured", exc=exc, op="inbox_store") from exc

    def _require_record(
        store: WhatsAppConnectionStore, *, connection_id: UUID, org_id: UUID, decrypt: bool = False
    ) -> WhatsAppConnectionRecord:
        try:
            record = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=decrypt)
        except WhatsAppConnectionStoreError as exc:
            raise integration_error("service_unavailable", exc=exc, op="inbox_record") from exc
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
            raise integration_error("invalid_request", exc=exc, op="inbox_page") from exc
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
            raise integration_error("invalid_request", exc=exc, op="inbox_page") from exc
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
        if not record.app_enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "app_disabled", "message": "This app is switched OFF for this WhatsApp line"},
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
        if on_message is not None:
            await notify_message(on_message, org_id, connection_id, fresh_chat, message)
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

    admin_dep = get_admin_user_org or get_current_user_org

    async def _call(hook: Callable[..., Any], *args: Any) -> None:
        out = await run_in_threadpool(hook, *args) if not _is_coro_fn(hook) else await hook(*args)
        if hasattr(out, "__await__"):
            await out

    # ─── per-chat agent pause ───────────────────────────────────────────
    if on_agent_pause is not None:

        @router.patch(f"{prefix}/{{connection_id}}/chats/{{chat_id:path}}/agent-paused", response_model=InboxChatOut)
        @access_tier('org', reason='org-scoped: the product\'s admin dependency (get_admin_user_org) gates it; connection checked against the caller org')
        async def set_agent_paused(
            connection_id: UUID,
            chat_id: str,
            body: AgentPausedIn,
            auth: tuple = Depends(admin_dep),
            conn_store: WhatsAppConnectionStore = Depends(_conn_store),
            chats: WhatsAppChatStore = Depends(_chat_store),
        ) -> InboxChatOut:
            org_id = resolve_org_id(auth[2])
            actor = _actor_of(auth)
            await run_in_threadpool(lambda: _require_record(conn_store, connection_id=connection_id, org_id=org_id))
            chat = await run_in_threadpool(
                lambda: chats.get_chat(org_id=org_id, connection_id=connection_id, chat_id=chat_id)
            )
            if chat is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chat not found")
            try:
                await _call(on_agent_pause, org_id, connection_id, chat, body.paused, actor)
            except Exception as exc:  # noqa: BLE001 - the product refused / failed: record nothing
                logger.warning("inbox agent-pause hook failed connection=%s: %s", connection_id, type(exc).__name__)
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail={"code": "agent_pause_failed", "message": "Could not change the agent state for this chat"},
                ) from exc
            saved = await run_in_threadpool(
                lambda: chats.set_agent_paused(
                    org_id=org_id, connection_id=connection_id, chat_id=chat_id, paused=body.paused, actor=actor
                )
            )
            if saved is None:  # deleted between the read and the write
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chat not found")
            if realtime is not None:
                await realtime.publish(connection_id, EVENT_CHAT_UPSERT, {"chat": saved.as_dict()})
            return InboxChatOut(**saved.as_dict())

    # ─── per-chat LGPD erasure ──────────────────────────────────────────
    if allow_chat_delete:

        @router.post(
            f"{prefix}/{{connection_id}}/chats/{{chat_id:path}}/apagar-dados", response_model=ChatDeletedOut
        )
        @access_tier('org', reason='org-scoped LGPD erasure: the product\'s admin dependency (get_admin_user_org) gates it; connection checked against the caller org')
        async def delete_chat(
            connection_id: UUID,
            chat_id: str,
            request: Request,
            auth: tuple = Depends(admin_dep),
            conn_store: WhatsAppConnectionStore = Depends(_conn_store),
            chats: WhatsAppChatStore = Depends(_chat_store),
        ) -> ChatDeletedOut:
            org_id = resolve_org_id(auth[2])
            actor = _actor_of(auth)
            await run_in_threadpool(lambda: _require_record(conn_store, connection_id=connection_id, org_id=org_id))
            chat = await run_in_threadpool(
                lambda: chats.get_chat(org_id=org_id, connection_id=connection_id, chat_id=chat_id)
            )
            if chat is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="chat not found")
            if on_delete_chat is not None:  # downstream data first: it may reference the chat being erased
                try:
                    await _call(on_delete_chat, org_id, connection_id, chat_id, actor)
                except Exception as exc:  # noqa: BLE001 - nothing erased; the call is retriable
                    logger.warning("inbox delete-chat hook failed connection=%s: %s", connection_id, type(exc).__name__)
                    raise HTTPException(
                        status.HTTP_502_BAD_GATEWAY,
                        detail={"code": "delete_chat_failed", "message": "Could not erase this conversation's data"},
                    ) from exc
            deleted = await run_in_threadpool(
                lambda: chats.delete_chat(org_id=org_id, connection_id=connection_id, chat_id=chat_id)
            )
            messages_deleted = deleted or 0
            await _audit_erasure(request, org_id, connection_id, chat_id, actor, messages_deleted)
            if realtime is not None:
                await realtime.publish(connection_id, EVENT_CHAT_DELETED, {"chat_id": chat_id})
            return ChatDeletedOut(messages_deleted=messages_deleted, chat_deleted=deleted is not None)

    async def _audit_erasure(
        request: Request, org_id: UUID, connection_id: UUID, chat_id: str, actor: Optional[str], count: int
    ) -> None:
        """ONE audit row, no content: the chat is identified by a salted-by-scope hash, never its JID/number."""
        ref = hashlib.sha256(f"{org_id}:{connection_id}:{chat_id}".encode()).hexdigest()[:16]
        logger.warning("whatsapp.chat_erased connection=%s org=%s chat_ref=%s messages=%d", connection_id, org_id, ref, count)
        sink = getattr(request.app.state, "audit_sink", None)
        if sink is None or not getattr(request.app.state, "audit_enabled", False):
            return
        await sink.record(AuditEntry(
            product_slug=audit_product_slug,
            method="POST",
            route_template=f"{prefix}/{{connection_id}}/chats/{{chat_id}}/apagar-dados",
            path_params={"connection_id": str(connection_id), "chat_ref": ref, "messages_deleted": str(count)},
            status=200,
            actor_kind="user",
            client_hint="whatsapp-chat-erasure",
            actor=AuditActor(user_id=actor or "", org_id=str(org_id), role="admin"),
        ))

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
        if record.session_role == "borrower":
            # backfill reads the whole WAHA history of a session this app does not own
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "session_borrowed", "message": "This line borrows another app's WhatsApp session"},
            )
        if is_backfill_running(connection_id):
            return BackfillStartedOut(status="already_running")
        client = _waha_client(record)

        async def _run() -> None:
            report = await backfill_connection(
                record=record, chat_store=chats, waha_client=client, lid_cache=lid_cache,
                should_store=should_store, **backfill_kwargs
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
            scheme="waha",
            bypass_when_unset=not require_webhook_hmac,
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
        if not record.app_enabled:
            # Per-app switch OFF: acknowledge (200, so WAHA does not retry) but store/notify NOTHING. Other apps
            # on the same session have their own webhook entry and are unaffected. A future per-chat dispatcher
            # fans out from exactly this point.
            return {"status": "disabled"}
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
            on_message=on_message,
            lid_cache=lid_cache,
            waha_client_factory=lambda rec: _client_for_identity(rec, store),
            should_store=should_store,  # PRE-STORE seam (default None = store all); see ingest.ShouldStore
        )
        if on_session_status is not None and result.status == "session":
            await _fire_session_status(on_session_status, record, body)
        return {"status": result.status}

    def _client_for_identity(rec: WhatsAppConnectionRecord, store: WhatsAppConnectionStore) -> Any:
        """WAHA client for @lid resolution (needs the decrypted key; the
        token-resolved record is not decrypted)."""
        full = store.get_connection(connection_id=rec.id, org_id=rec.org_id, decrypt=True)
        if full is None or not full.base_url:
            return None
        return waha_client_factory(base_url=full.base_url, api_key=full.api_key, session=full.session_name)

    if webhook_only:
        keep = f"{webhook_path_prefix}/"
        router.routes[:] = [r for r in router.routes if str(getattr(r, "path", "")).startswith(keep)]
    elif read_only:
        dead = {(m, f"{prefix}{tail}") for m, tail in READ_ONLY_UNMOUNTED_ROUTES}
        router.routes[:] = [
            r for r in router.routes
            if not any((m, getattr(r, "path", None)) in dead for m in getattr(r, "methods", ()) or ())
        ]
    return router


class WebhookHmacRequired(RuntimeError):
    """``require_webhook_hmac=True`` in a deploy without a webhook HMAC secret: refuse to boot (fail-closed)."""


def _is_coro_fn(fn: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


def _actor_of(auth: tuple) -> Optional[str]:
    user = auth[0]
    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return str(uid) if uid else None


async def _fire_session_status(callback: Callable[[WhatsAppConnectionRecord, str], Any], record: Any, body: dict) -> None:
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    status_value = str(payload.get("status") or body.get("status") or "")
    try:
        out = callback(record, status_value)
        if hasattr(out, "__await__"):
            await out
    except Exception as exc:  # noqa: BLE001 - best-effort hook; the webhook must still ack 200
        logger.warning("on_session_status failed connection=%s: %s", record.id, type(exc).__name__)


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
