"""Per-user, multi-session WAHA connection management — `/api/whatsapp/connections`.

Lets an operator manage MANY WhatsApp connections ("lines") from the product
UI instead of the WAHA dashboard. Each line carries its own WAHA server URL +
session name + API key (Fernet-encrypted at rest, owner-scoped per user). The
router exposes:

    GET    /api/whatsapp/connections              → list[WhatsAppConnectionOut]
    POST   /api/whatsapp/connections              → WhatsAppConnectionOut (201)
    PATCH  /api/whatsapp/connections/{id}         → WhatsAppConnectionOut
    DELETE /api/whatsapp/connections/{id}         → 204

    GET    /api/whatsapp/connections/{id}/status  → live WAHA session state
    GET    /api/whatsapp/connections/{id}/qr      → live QR (base64 PNG)
    POST   /api/whatsapp/connections/{id}/start   → create/start the session
    POST   /api/whatsapp/connections/{id}/restart → restart the session
    POST   /api/whatsapp/connections/{id}/logout  → unlink the account
    POST   /api/whatsapp/connections/{id}/recover → run the start→restart→
                                                     logout+start recovery
                                                     ladder (the UI's primary
                                                     reconnect action)
    POST   /api/whatsapp/connections/{id}/webhook → wire the inbound webhook

    GET    /api/whatsapp/connections/{id}/chats                    → paginated inbox
    GET    /api/whatsapp/connections/{id}/chats/{chatId}/messages  → paginated thread
    POST   /api/whatsapp/connections/{id}/chats/{chatId}/read      → zero the badge
    GET    /api/whatsapp/connections/{id}/stream                   → SSE (text/event-stream)

CRUD persists to ``social_wiring.whatsapp_connections`` via the
:class:`WhatsAppConnectionStore` (resolved through the ``get_connection_store``
DI seam); the live side decrypts the line's API key just-in-time and drives
the seed ``WahaClient`` (the same client the single-session seed
``whatsapp_admin_router`` uses, here parameterized per line through the
``get_waha_client_factory`` DI seam).

WAHA IS NOT ON THE READ PATH (whatsapp-realtime-inbox, Slice 5): ``/chats``
and ``/chats/{chatId}/messages`` read exclusively from Postgres —
``social_wiring.whatsapp_chats`` (migration 040, via :class:`WhatsAppChatStore`)
and ``conversation_messages`` (its migration-040 ``chat_id``/``ack``/``acked_at``
columns, via the router-local :class:`_ChatMessagesReader`). Realtime updates
ride the seed's provider-neutral bus (``app.services.whatsapp_realtime`` +
``noctusai_lib.realtime``) — ``/stream`` mounts ``create_sse_router`` scoped
per connection, ownership-checked the same way every other live op is.

Auth: ``Depends(get_current_user_org)`` → ``(user, token, org_id)``; every
store call additionally scopes by the resolved ``user_id`` so lines are
isolated per user (the canonical pattern — see
``KB § PATTERNS/backend.md § Auth — canonical pattern``). DI seams over
patching per ``KB § PATTERNS/di-test-seam.md``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
from typing import Any
from uuid import NAMESPACE_OID, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    get_whatsapp_client,
)
from noctusai_lib.realtime import create_sse_router

from app.config import SocialWiringSettings, settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_settings,
)
from app.schemas.whatsapp_connection import (
    AutoReplyToggleOut,
    AutoReplyToggleRequest,
    BoundChat,
    ChatDTO,
    ChatReadOut,
    ChatReadRequest,
    ChatsPage,
    DEFAULT_WHATSAPP_WEBHOOK_EVENTS,
    MessageDTO,
    MessageOut,
    MessagesPage,
    SendMessageRequest,
    WhatsAppConnectionApiKeyOut,
    WhatsAppConnectionCreate,
    WhatsAppConnectionOut,
    WhatsAppConnectionQrOut,
    WhatsAppConnectionRecoverOut,
    WhatsAppConnectionStatusOut,
    WhatsAppConnectionUpdate,
    WhatsAppWebhookConfigRequest,
    WhatsAppWebhookResultOut,
)
from app.services.credential_vault import CredentialStoreError, EncryptionNotConfigured
from app.services.message_store import MessageStore
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import (
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    build_whatsapp_connection_store,
)
from app.services.whatsapp_realtime import (
    EVENT_CHAT_READ,
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
    get_whatsapp_bus,
    publish_whatsapp_event,
    whatsapp_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp/connections", tags=["WhatsApp"])


# ─── DI seams ───────────────────────────────────────────────────────────────
def get_connection_store(
    cfg: SocialWiringSettings = Depends(get_settings),
) -> WhatsAppConnectionStore:
    """Yield a wired :class:`WhatsAppConnectionStore`, mapping the
    ENCRYPTION_KEY config-gap to a 503. The DI seam tests override via
    ``app.dependency_overrides[get_connection_store]`` with a SQLite-backed
    store (real CRUD persistence) — no self-monkeypatch. Per
    ``KB § PATTERNS/di-test-seam.md`` (Class-B, service DI)."""
    try:
        return build_whatsapp_connection_store(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def get_waha_client_factory():
    """DI seam for the per-line WAHA client factory (default: the seed
    ``get_whatsapp_client``). Tests override via ``app.dependency_overrides``
    to inject a deterministic ``FakeWahaClient`` producer — exercising the
    router logic without real HTTP and without patching the external
    integration. Per ``KB § PATTERNS/di-test-seam.md`` (Class-B)."""
    return get_whatsapp_client


def get_chat_store_for_org(org_id: UUID) -> WhatsAppChatStore:
    """Build a :class:`WhatsAppChatStore` bound to the calling user's org.

    Same shape as :func:`get_message_store_for_org` below: not a FastAPI
    ``Depends`` itself (``org_id`` is resolved per-route after the auth dep
    runs). Tests override the factory (see :func:`get_chat_store_factory`)
    with one bound to a SQLite-backed stand-in."""
    return WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=org_id)


def get_chat_store_factory():
    """DI seam — returns the ``get_chat_store_for_org`` factory.

    Override via ``app.dependency_overrides[get_chat_store_factory]`` to
    inject a deterministic store in tests. Per ``KB § PATTERNS/di-test-seam.md``
    (Class-B)."""
    return get_chat_store_for_org


_CHAT_MESSAGES_SCHEMA = "social_wiring"
_CHAT_MESSAGES_TABLE = "conversation_messages"


class _ChatMessagesReader:
    """Thin, router-local read seam over ``conversation_messages`` scoped by
    the migration-040 ``chat_id`` column (+ ``ack``/``acked_at``).

    Colocated here rather than folded into :class:`MessageStore` — that
    store is the ingest/backfill slice's territory (``raw_sender``-keyed,
    JSON-parses ``structured_payload`` itself); this reader is the
    connections-router's read-only thread view over the NEW indexed
    ``(connection_id, chat_id, created_at DESC)`` shape migration 040 added
    specifically for ``GET /chats/{id}/messages`` (see that migration's
    header note — this IS the query the index exists for).
    """

    def __init__(self, *, admin_supabase, org_id: UUID):
        self._admin = admin_supabase
        self._org_id = org_id

    def list_messages(
        self,
        *,
        connection_id: UUID,
        chat_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Newest-first page of one chat thread, canonical ``chat_id`` only
        (no JID-alias fan-out — pre-migration-040 rows carry ``chat_id IS
        NULL`` and are not backfilled, so they simply do not surface here;
        see the migration's header note). ``before`` is an ISO 8601 UTC
        cursor — page toward older history."""
        query = (
            self._admin.schema(_CHAT_MESSAGES_SCHEMA)
            .table(_CHAT_MESSAGES_TABLE)
            .select(
                "id, chat_id, direction, body, ack, acked_at, created_at, "
                "provider_message_id, structured_payload"
            )
            .eq("connection_id", str(connection_id))
            .eq("org_id", str(self._org_id))
            .eq("chat_id", chat_id)
        )
        if before:
            query = query.lt("created_at", before)
        response = (
            query.order("created_at", desc=True)
            .limit(max(1, min(limit, 200)))
            .execute()
        )
        return list(response.data or [])


def get_chat_messages_reader_for_org(org_id: UUID) -> _ChatMessagesReader:
    return _ChatMessagesReader(admin_supabase=get_admin_client(), org_id=org_id)


def get_chat_messages_reader_factory():
    """DI seam — returns the ``get_chat_messages_reader_for_org`` factory.
    Same Class-B pattern as :func:`get_chat_store_factory` /
    :func:`get_message_store_factory`."""
    return get_chat_messages_reader_for_org


# ─── helpers ──────────────────────────────────────────────────────────────
def _coerce_user_uuid(user: Any) -> UUID:
    """Resolve the owner UUID from whatever shape the auth dep returned.

    Real Supabase users carry a UUID id; local-dev fixtures may use opaque
    strings — derive a stable UUID via uuid5 so the NOT-NULL ``user_id``
    column always gets a value (mirrors ``coerce_org_uuid``)."""
    raw = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return uuid5(NAMESPACE_OID, str(raw))


def _out(record: WhatsAppConnectionRecord) -> WhatsAppConnectionOut:
    return WhatsAppConnectionOut(
        id=record.id,
        label=record.label,
        base_url=record.base_url,
        session_name=record.session_name,
        webhook_url=record.webhook_url,
        created_at=record.created_at,
        updated_at=record.updated_at,
        auto_reply_enabled=record.auto_reply_enabled,
        # Migration 016 — per-connection intake config.
        authorized_numbers=record.authorized_numbers,
        bound_chats=[BoundChat(**bc) for bc in record.bound_chats],
        # Migration 017 — optional cliente ownership.
        marca_id=record.marca_id,
    )


def _require_record(
    store: WhatsAppConnectionStore,
    *,
    connection_id: UUID,
    org_id: UUID,
    user_id: UUID,
    decrypt: bool = False,
) -> WhatsAppConnectionRecord:
    """Fetch a line owner-scoped or 404. ``decrypt=True`` for live WAHA ops;
    a key-mismatch on decrypt surfaces as a 503 config gap."""
    try:
        record = store.get_connection(
            connection_id=connection_id,
            org_id=org_id,
            user_id=user_id,
            decrypt=decrypt,
        )
    except CredentialStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="connection not found"
        )
    return record


def _waha_client(record: WhatsAppConnectionRecord, factory: Any):
    """Build a WAHA client bound to this line's decrypted credentials."""
    return factory(
        base_url=record.base_url or None,
        api_key=record.api_key,
        session=record.session_name,
    )


def _status_from_session(
    payload: dict[str, Any], *, connection_id: UUID, session: str
) -> WhatsAppConnectionStatusOut:
    status_str = payload.get("status")
    me = payload.get("me") if isinstance(payload.get("me"), dict) else None
    return WhatsAppConnectionStatusOut(
        connection_id=connection_id,
        status=status_str,
        paired=bool(me) and status_str == "WORKING",
        me_id=(me or {}).get("id"),
        me_name=(me or {}).get("pushName"),
        session=session,
    )


# ─── CRUD ──────────────────────────────────────────────────────────────────
@router.get("", response_model=list[WhatsAppConnectionOut])
async def list_connections(
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    # Migration 017 — optional ?marca_id= filter (was `client_id` until 046).
    marca_id: UUID | None = Query(default=None, description="Filter by marca id."),
) -> list[WhatsAppConnectionOut]:
    user, _token, raw_org = auth
    records = store.list_connections(
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        marca_id=marca_id,
    )
    return [_out(r) for r in records]


@router.post("", response_model=WhatsAppConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    body: WhatsAppConnectionCreate,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    cfg: SocialWiringSettings = Depends(get_settings),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionOut:
    """Create a new WAHA connection line.

    Accepts ONLY ``label`` and ``api_key``; every other field is derived
    server-side:

    - ``base_url``      — ``cfg.waha_base_url`` (the shared WAHA server).
                          Empty → 503 (no WAHA configured).
    - ``session_name``  — ``cfg.waha_session`` (``"default"`` by default).
                          WAHA Core only permits the single ``default`` session,
                          so the line drives it directly. (On WAHA Plus, where
                          multiple named sessions are allowed, point
                          ``WAHA_SESSION`` at a per-tenant value to isolate
                          accounts.)
    - ``webhook_token`` — ``secrets.token_urlsafe(24)`` opaque routing token.
    - ``webhook_url``   — ``resolve_product_url('social-wiring') + /api/whatsapp/webhook/{token}``.
                          ValueError from resolver → 503.

    After persisting: calls ``start_session()`` then ``set_webhook()`` on the
    WAHA client. WAHA 409/422 on start are tolerated (handled inside the
    client). Real WAHA errors on webhook → 502.
    """
    user, _token, raw_org = auth

    # ── 1. Resolve the WAHA server ─────────────────────────────────────
    base_url = (cfg.waha_base_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WAHA server not configured (WAHA_BASE_URL is empty)",
        )

    # ── 2. Resolve the WAHA session name ───────────────────────────────
    # WAHA Core supports ONLY the single "default" session, so we drive the
    # configured session (default: "default") rather than minting a unique
    # per-connection name. WAHA Plus users can repoint WAHA_SESSION per tenant.
    session_name = (cfg.waha_session or "default").strip()

    # ── 3. Mint webhook token + build public URL ────────────────────────
    webhook_token = secrets.token_urlsafe(24)
    try:
        product_base = resolve_product_url("social-wiring")
    except ValueError as exc:
        logger.error("Cannot resolve social-wiring product URL for webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Cannot build webhook URL: product URL not configured "
                "(set PRODUCT_URL_SOCIAL_WIRING or PRODUCT_URL_PATTERN)"
            ),
        ) from exc
    webhook_url = f"{product_base}/api/whatsapp/webhook/{webhook_token}"

    # ── 4. Persist ─────────────────────────────────────────────────────
    record = store.create_connection(
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        label=body.label.strip(),
        base_url=base_url,
        api_key=body.api_key.strip(),
        session_name=session_name,
        webhook_url=webhook_url,
        webhook_token=webhook_token,
        # Migration 017 — thread optional cliente id through at creation.
        marca_id=body.marca_id,
    )

    # ── 5. Wire WAHA: start session then register webhook ───────────────
    # Build the client directly from the request-time plain key (the stored
    # record has api_key=None; we have the plain key in body). This avoids
    # an unnecessary decrypt round-trip and keeps the pattern clean.
    client = waha_factory(
        base_url=base_url or None,
        api_key=body.api_key.strip(),
        session=session_name,
    )
    # start_session tolerates 409/422 (already started) internally.
    try:
        await client.start_session()
    except Exception as exc:
        logger.warning(
            "WAHA start_session failed for new connection %s (session=%s): %s",
            record.id, session_name, exc,
        )
        # Non-fatal: the operator can trigger start manually via /start.
        # Do not roll back the DB record — it's valid to create and start later.

    try:
        # Slice 5 — register the FULL inbound event set (message, message.any,
        # message.ack, message.reaction, session.status), not just the two
        # this connection used to boot with: message.ack/reaction feed the
        # realtime bus, and message.any is the WAHA echo of OUR OWN outbound
        # sends that keeps `whatsapp_chats` current without /send having to
        # write it directly (see `DEFAULT_WHATSAPP_WEBHOOK_EVENTS`).
        await client.set_webhook(webhook_url, DEFAULT_WHATSAPP_WEBHOOK_EVENTS)
    except Exception as exc:
        logger.error(
            "WAHA set_webhook failed for connection %s (session=%s): %s",
            record.id, session_name, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WAHA webhook registration failed: {exc}",
        ) from exc

    return _out(record)


@router.patch("/{connection_id}", response_model=WhatsAppConnectionOut)
async def update_connection(
    connection_id: UUID,
    body: WhatsAppConnectionUpdate,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> WhatsAppConnectionOut:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    # 404 early if the line isn't the caller's.
    _require_record(store, connection_id=connection_id, org_id=org_id, user_id=user_id)

    # Use model_fields_set to distinguish "field absent from request" (keep
    # current value) from "field supplied as []" (clear → means allow-all /
    # listen-to-all).  We must NOT treat an explicit [] as "not supplied".
    _extra: dict = {}
    if "authorized_numbers" in body.model_fields_set and body.authorized_numbers is not None:
        _extra["authorized_numbers"] = body.authorized_numbers
    if "bound_chats" in body.model_fields_set and body.bound_chats is not None:
        _extra["bound_chats"] = [bc.model_dump() for bc in body.bound_chats]
    # Migration 017 — marca_id three-state via _UNSET sentinel.
    # Absent from request  → keep current (_UNSET propagated).
    # Explicit null        → clear the link (None propagated).
    # UUID value           → assign to that marca (UUID propagated).
    if "marca_id" in body.model_fields_set:
        _extra["marca_id"] = body.marca_id  # None (clear) or UUID (assign)

    record = store.update_connection(
        connection_id=connection_id,
        org_id=org_id,
        user_id=user_id,
        label=body.label.strip() if body.label is not None else None,
        base_url=body.base_url.strip() if body.base_url is not None else None,
        session_name=body.session_name.strip() if body.session_name is not None else None,
        api_key=body.api_key.strip() if body.api_key is not None else None,
        webhook_url=body.webhook_url if body.webhook_url is not None else None,
        **_extra,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="connection not found"
        )
    return _out(record)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> Response:
    user, _token, raw_org = auth
    deleted = store.delete_connection(
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="connection not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Live WAHA ops (per line) ───────────────────────────────────────────────
@router.get("/{connection_id}/status", response_model=WhatsAppConnectionStatusOut)
async def get_connection_status(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionStatusOut:
    user, _token, raw_org = auth
    record = _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        decrypt=True,
    )
    client = _waha_client(record, waha_factory)
    try:
        payload = await client.get_session()
    except Exception as exc:  # noqa: BLE001 — surfaced in DTO, not swallowed
        logger.warning("WAHA status probe failed for line %s: %s", connection_id, exc)
        return WhatsAppConnectionStatusOut(
            connection_id=connection_id, session=record.session_name, error=str(exc)
        )
    return _status_from_session(
        payload, connection_id=connection_id, session=record.session_name
    )


@router.get("/{connection_id}/api-key", response_model=WhatsAppConnectionApiKeyOut)
async def reveal_connection_api_key(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> WhatsAppConnectionApiKeyOut:
    """Reveal the decrypted API key for ONE owner-scoped line.

    The single, deliberate place a stored secret leaves the backend — gated by
    the same owner scope as every live op (``user_id`` + ``org_id`` filter) and
    driven only by an explicit user action (the eye toggle in the connection
    modal). A decrypt failure (ENCRYPTION_KEY drift / tampered ciphertext)
    surfaces as 503 via ``_require_record(decrypt=True)``; a non-owner / missing
    line is 404. Reveal-only: never call this on a list/get path.
    """
    user, _token, raw_org = auth
    record = _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        decrypt=True,
    )
    return WhatsAppConnectionApiKeyOut(
        connection_id=connection_id, api_key=record.api_key or ""
    )


@router.get("/{connection_id}/qr", response_model=WhatsAppConnectionQrOut)
async def get_connection_qr(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionQrOut:
    user, _token, raw_org = auth
    record = _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        decrypt=True,
    )
    client = _waha_client(record, waha_factory)
    try:
        png = await client.get_qr()
    except WahaSessionNotReady as exc:
        # Paired / starting — nothing to scan. 200 so the UI keeps one contract.
        return WhatsAppConnectionQrOut(
            connection_id=connection_id, scannable=False, status=exc.status
        )
    except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WAHA QR fetch failed: {exc}",
        ) from exc
    return WhatsAppConnectionQrOut(
        connection_id=connection_id,
        scannable=True,
        status="SCAN_QR_CODE",
        png_base64=base64.b64encode(png).decode("ascii"),
    )


async def _session_action(
    *,
    connection_id: UUID,
    store: WhatsAppConnectionStore,
    auth: tuple,
    action: str,
    waha_factory: Any,
) -> WhatsAppConnectionStatusOut:
    """Shared driver for start / restart / logout — call the action, then
    re-read + return the live session state. WAHA failures → 502."""
    user, _token, raw_org = auth
    record = _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        decrypt=True,
    )
    client = _waha_client(record, waha_factory)
    try:
        await getattr(client, action)()
        payload = await client.get_session()
    except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WAHA {action} failed: {exc}",
        ) from exc
    return _status_from_session(
        payload, connection_id=connection_id, session=record.session_name
    )


@router.post("/{connection_id}/start", response_model=WhatsAppConnectionStatusOut)
async def start_connection(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionStatusOut:
    return await _session_action(
        connection_id=connection_id, store=store, auth=auth,
        action="start_session", waha_factory=waha_factory,
    )


@router.post("/{connection_id}/restart", response_model=WhatsAppConnectionStatusOut)
async def restart_connection(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionStatusOut:
    return await _session_action(
        connection_id=connection_id, store=store, auth=auth,
        action="restart_session", waha_factory=waha_factory,
    )


@router.post("/{connection_id}/logout", response_model=WhatsAppConnectionStatusOut)
async def logout_connection(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionStatusOut:
    return await _session_action(
        connection_id=connection_id, store=store, auth=auth,
        action="logout_session", waha_factory=waha_factory,
    )


@router.post("/{connection_id}/recover", response_model=WhatsAppConnectionRecoverOut)
async def recover_connection(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppConnectionRecoverOut:
    """Run the seed's start→restart→logout+start recovery ladder and return
    the converged session state. This is the UI's PRIMARY reconnect action
    going forward — ``/start``, ``/restart``, ``/logout`` remain individually
    callable (unchanged) for an operator who wants one specific rung.

    Why this exists: a session with stored-but-dead credentials answers
    ``restart`` by retrying those dead credentials and hangs in ``STARTING``
    for minutes before WAHA's own watchdog force-stops it back to ``FAILED``
    (proven twice on the live fleet session's logs) — only ``logout``
    actually clears the stored credentials so NOWEB can re-enter
    ``SCAN_QR_CODE``. The ladder converges regardless of which single rung
    is individually "the fix" for a given session's state.
    """
    user, _token, raw_org = auth
    record = _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
        decrypt=True,
    )
    client = _waha_client(record, waha_factory)
    try:
        outcome = await client.recover_session()
    except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WAHA recover failed: {exc}",
        ) from exc

    bus = get_whatsapp_bus(settings.redis_url)
    await publish_whatsapp_event(
        bus,
        connection_id=connection_id,
        event=EVENT_SESSION_STATUS,
        payload={
            "connection_id": str(connection_id),
            "status": outcome.get("status"),
            "paired": bool(outcome.get("paired")),
            "stage": outcome.get("stage"),
        },
    )
    return WhatsAppConnectionRecoverOut(
        connection_id=connection_id,
        status=outcome.get("status"),
        paired=bool(outcome.get("paired")),
        stage=outcome.get("stage") or "",
    )


@router.post("/{connection_id}/webhook", response_model=WhatsAppWebhookResultOut)
async def configure_connection_webhook(
    connection_id: UUID,
    body: WhatsAppWebhookConfigRequest,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> WhatsAppWebhookResultOut:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    record = _require_record(
        store, connection_id=connection_id, org_id=org_id, user_id=user_id, decrypt=True
    )
    client = _waha_client(record, waha_factory)
    url = body.url.strip()
    try:
        result = await client.set_webhook(url, body.events)
    except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WAHA webhook config failed: {exc}",
        ) from exc
    # Persist the last-wired webhook so the line remembers it across reloads.
    store.update_connection(
        connection_id=connection_id, org_id=org_id, user_id=user_id, webhook_url=url
    )
    waha_status = result.get("status") if isinstance(result, dict) else None
    return WhatsAppWebhookResultOut(
        connection_id=connection_id,
        ok=True,
        url=url,
        events=body.events,
        status=waha_status,
    )


# ── Per-connection chat inbox ────────────────────────────────────────────────
# DI seam: MessageStore is built here (admin client, owner's org_id). Tests
# override ``get_message_store_for_org`` via app.dependency_overrides with a
# SQLite-backed store — same Class-B pattern as get_connection_store above.

def get_message_store_for_org(org_id: UUID) -> MessageStore:
    """Build a MessageStore bound to the calling user's org.

    Not a FastAPI Depends itself (org_id is resolved per-route after the
    auth dep runs). Tests override the factory via a fixture that returns a
    SQLiteClient-backed store (real persistence, no Supabase).
    """
    return MessageStore(admin_supabase=get_admin_client(), org_id=org_id)


# Injectable seam so tests can swap the factory.
def get_message_store_factory():
    """DI seam — returns the ``get_message_store_for_org`` factory.

    Override via ``app.dependency_overrides[get_message_store_factory]``
    to inject a deterministic in-memory or SQLite store in tests.
    """
    return get_message_store_for_org


def _message_dto_from_row(row: dict[str, Any]) -> MessageDTO:
    """Map one ``conversation_messages`` row (migration-040 shape) to the
    wire ``MessageDTO``. ``structured_payload`` may arrive as a JSON string
    (Postgres/PostgREST) or already-decoded (test doubles) — normalise
    defensively rather than assume one shape."""
    sp = row.get("structured_payload")
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except (TypeError, ValueError):
            sp = None
    return MessageDTO(
        id=str(row.get("id")),
        provider_message_id=row.get("provider_message_id"),
        chat_id=row.get("chat_id") or "",
        direction=row.get("direction"),
        body=row.get("body") or "",
        ack=row.get("ack"),
        acked_at=row.get("acked_at"),
        created_at=row.get("created_at") or "",
        structured_payload=sp,
    )


@router.get("/{connection_id}/chats", response_model=ChatsPage)
async def list_chats(
    connection_id: UUID,
    limit: int = Query(default=30, ge=1, le=200),
    before: str | None = Query(default=None, description="ISO 8601 UTC keyset cursor."),
    archived: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    chat_store_factory: Any = Depends(get_chat_store_factory),
) -> ChatsPage:
    """Paginated inbox — pure Postgres (``social_wiring.whatsapp_chats``,
    migration 040). WAHA is NEVER called on this path (see the module
    docstring's "WAHA IS NOT ON THE READ PATH" note).

    Newest-activity-first. ``next_before`` is the last item's
    ``last_message_at`` in THIS page when the page was full (``limit``
    items returned) — pass it back as ``before`` to page further into
    history; ``null`` means there is no more history to load.
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    _require_record(store, connection_id=connection_id, org_id=org_id, user_id=user_id)

    chat_store: WhatsAppChatStore = chat_store_factory(org_id)
    summaries = chat_store.list_chats(
        connection_id=connection_id, limit=limit, before=before, archived=archived,
    )
    items = [ChatDTO(**s.as_dict()) for s in summaries]
    next_before = items[-1].last_message_at if len(items) == limit else None
    return ChatsPage(items=items, next_before=next_before)


@router.post("/{connection_id}/chats/{chat_id:path}/read", response_model=ChatReadOut)
async def mark_chat_read(
    connection_id: UUID,
    chat_id: str,
    body: ChatReadRequest,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    chat_store_factory: Any = Depends(get_chat_store_factory),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> ChatReadOut:
    """Zero a chat's unread badge and mirror the read-receipt to WAHA.

    The Postgres write (the badge-clearing side of the contract) happens
    first and is what this endpoint's response reflects; ``send_seen`` on
    the live WAHA session then fires in the BACKGROUND
    (``asyncio.create_task`` — same fire-and-forget shape
    ``whatsapp_intake_service`` already uses) and is NEVER awaited here — a
    slow or dead WAHA must not make clearing a badge feel slow, and a
    ``send_seen`` failure is logged, never raised, since the badge is
    already durably cleared.

    ⚠️ ``send_seen`` marks the chat read on the operator's REAL WhatsApp
    phone (blue ticks on the device) — this is INTENDED and user-approved,
    not a bug to "fix" into a no-op.

    Unknown ``chat_id`` (no ``whatsapp_chats`` row yet) → 404, not 500.
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    record = _require_record(
        store, connection_id=connection_id, org_id=org_id, user_id=user_id, decrypt=True,
    )

    chat_store: WhatsAppChatStore = chat_store_factory(org_id)
    try:
        summary = chat_store.mark_read(
            connection_id=connection_id,
            chat_id=chat_id,
            up_to_message_id=body.up_to_message_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    bus = get_whatsapp_bus(settings.redis_url)
    await publish_whatsapp_event(
        bus,
        connection_id=connection_id,
        event=EVENT_CHAT_READ,
        payload={
            "chat_id": chat_id,
            "unread_count": 0,
            "last_read_at": summary.last_read_at,
        },
    )

    client = _waha_client(record, waha_factory)
    asyncio.create_task(_fire_send_seen(client, chat_id=chat_id, connection_id=connection_id))

    return ChatReadOut(chat_id=chat_id, unread_count=0, last_read_at=summary.last_read_at)


async def _fire_send_seen(client: Any, *, chat_id: str, connection_id: UUID) -> None:
    """Background-only: mirror a read-receipt to WAHA. Never on the response
    path, never raised — see ``mark_chat_read``'s docstring for why."""
    try:
        await client.send_seen(chat_id)
    except Exception as exc:  # noqa: BLE001 — best-effort background op
        logger.warning(
            "send_seen failed for chat %s connection %s (badge already "
            "cleared in Postgres, not retried): %s",
            chat_id, connection_id, exc,
        )


@router.get(
    "/{connection_id}/chats/{chat_id:path}/messages", response_model=MessagesPage
)
async def list_messages(
    connection_id: UUID,
    chat_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None, description="ISO 8601 UTC keyset cursor."),
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    reader_factory: Any = Depends(get_chat_messages_reader_factory),
) -> MessagesPage:
    """Paginated thread — pure Postgres via the migration-040
    ``(connection_id, chat_id, created_at DESC)`` index. WAHA is NEVER
    called on this path; no JID-alias fan-out (canonical ``chat_id`` only —
    pre-migration-040 rows carry ``chat_id IS NULL`` and are not backfilled,
    per that migration's header note, so they do not surface here).

    Newest-first per page (mirrors ``GET /chats``'s pagination shape).
    ``next_before`` is the last item's ``created_at`` in THIS page when the
    page was full; ``null`` means there is no more history.
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    _require_record(store, connection_id=connection_id, org_id=org_id, user_id=user_id)

    reader = reader_factory(org_id)
    rows = reader.list_messages(
        connection_id=connection_id, chat_id=chat_id, limit=limit, before=before,
    )
    items = [_message_dto_from_row(r) for r in rows]
    next_before = items[-1].created_at if len(items) == limit else None
    return MessagesPage(items=items, next_before=next_before)


@router.post(
    "/{connection_id}/chats/{chat_id:path}/send",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    connection_id: UUID,
    chat_id: str,
    body: SendMessageRequest,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
    msg_store_factory: Any = Depends(get_message_store_factory),
    chat_store_factory: Any = Depends(get_chat_store_factory),
    settings: SocialWiringSettings = Depends(get_settings),
) -> MessageOut:
    """Send a text message on this connection to the given chatId.

    Builds a WAHA client from the connection's decrypted credentials, calls
    ``send_text``, persists the outbound message tagged with connection_id,
    and returns the stored ``MessageOut``.

    On WAHA failure returns 502 with ``{"error":{"code":"waha_send_failed",
    "message":"…"}}``.  Empty ``text`` is rejected with 422 before WAHA is
    called.
    """
    import datetime as _dt

    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    record = _require_record(
        store, connection_id=connection_id, org_id=org_id, user_id=user_id, decrypt=True
    )

    client = _waha_client(record, waha_factory)
    try:
        result = await client.send_text(chat_id, body.text)
    except Exception as exc:
        logger.error(
            "WAHA send_text failed for connection %s chatId %s: %s",
            connection_id, chat_id, exc,
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": {"code": "waha_send_failed", "message": str(exc)}},
        )

    # Persist outbound tagged with connection_id. Do NOT persist on failure
    # (the raise above ensures we only reach here on success).
    from app.schemas.whatsapp import extract_waha_message_id  # local import avoids circular
    provider_message_id = (
        extract_waha_message_id(result) if isinstance(result, dict) else None
    )
    # session_id: the direct JID form works here — the chat inbox queries
    # by raw_sender (not session_id), so the exact canonical form is not
    # critical for the inbox read path. The chatbot recall path is separate.
    session_id = chat_id
    sent_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    msg_store: MessageStore = msg_store_factory(org_id)
    stored = msg_store.record(
        session_id=session_id,
        raw_sender=chat_id,
        direction="outbound",
        body=body.text,
        provider_message_id=provider_message_id,
        authorized=True,
        connection_id=connection_id,
        # 🔴 MUST be stamped HERE, at first write. The thread read path queries
        # by chat_id alone, and this row is keyed by UNIQUE(provider_message_id)
        # — so WAHA's own `message.any` echo of this same send is dropped as a
        # duplicate and can never backfill the column. Omit it and the message
        # the user just sent is invisible in its own thread permanently, not
        # merely until the echo lands.
        chat_id=chat_id,
    )

    # Fold the send into the conversation row + push it to subscribers, exactly
    # as the inbound webhook does. Without this the sender's own list entry
    # would not move until the echo webhook arrived — and on a connection whose
    # webhook is misconfigured, never.
    chat_store: WhatsAppChatStore = chat_store_factory(org_id)
    summary = chat_store.record_message(
        connection_id=connection_id,
        chat_id=chat_id,
        direction="outbound",
        body=body.text,
        created_at=sent_at,
    )

    bus = get_whatsapp_bus(settings.redis_url)
    await publish_whatsapp_event(
        bus,
        connection_id=connection_id,
        event=EVENT_MESSAGE_NEW,
        payload={"chat_id": chat_id, "message": stored.as_message_dto()},
    )
    await publish_whatsapp_event(
        bus,
        connection_id=connection_id,
        event=EVENT_CHAT_UPSERT,
        payload=summary.as_dict(),
    )
    # Re-read the created_at from the store so the response timestamp is
    # accurate. We do a single list_messages call scoped to the just-inserted
    # id via the raw list (no extra DB round-trip in the SQLite test path).
    # In production Supabase the insert returns the row; we use the store's
    # result id + the sent_at clock we captured pre-send as a best-effort ISO.
    return MessageOut(
        id=str(stored.id),
        chat_id=chat_id,
        direction="outbound",
        body=body.text,
        created_at=sent_at,
        provider_message_id=stored.provider_message_id,
        structured_payload=None,
    )


@router.put("/{connection_id}/auto-reply", response_model=AutoReplyToggleOut)
async def toggle_auto_reply(
    connection_id: UUID,
    body: AutoReplyToggleRequest,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> AutoReplyToggleOut:
    """Toggle the per-connection chatbot auto-reply gate.

    ``enabled: true``  → the existing chatbot runs on inbound messages.
    ``enabled: false`` → inbound is stored but NO auto-reply fires (default).
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    # Ownership check — ensures the connection exists and belongs to this user.
    _require_record(store, connection_id=connection_id, org_id=org_id, user_id=user_id)

    record = store.update_auto_reply(
        connection_id=connection_id,
        org_id=org_id,
        user_id=user_id,
        enabled=body.enabled,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="connection not found"
        )
    return AutoReplyToggleOut(
        connection_id=connection_id,
        auto_reply_enabled=record.auto_reply_enabled,
    )


# ── Realtime stream (SSE) ────────────────────────────────────────────────────
# `create_sse_router` (noctusai_lib.realtime) captures its `bus` argument
# ONCE at router-construction time (this module's import) — it is not a
# per-request `Depends` resolution, so `settings.redis_url` is read directly
# from the singleton here rather than through the `Depends(get_settings)`
# seam every other endpoint in this file uses (mirrors the seed's own
# docstring recipe: `bus = get_realtime_bus(settings.redis_url)` at module
# scope). `_WhatsAppBusProxy` exists ONLY so tests can still swap the target
# bus after this router (and the sub-router `create_sse_router` builds
# around it) already exist — a genuinely-live bus cannot be exercised
# end-to-end through `TestClient` at all (its `subscribe()` never
# terminates; see `noctusai_lib.realtime`'s own test suite's `_FiniteBus`
# for the same constraint). Production never reassigns `_whatsapp_bus`
# after startup, so the indirection is free there.
_whatsapp_bus = get_whatsapp_bus(settings.redis_url)


class _WhatsAppBusProxy:
    """Delegates to whatever module-level ``_whatsapp_bus`` CURRENTLY points
    at, read at call time rather than captured once — see the section note
    above for why this indirection exists."""

    async def publish(self, scope: str, event: str, payload: dict) -> str | None:
        return await _whatsapp_bus.publish(scope, event, payload)

    def subscribe(self, scope: str, *, last_event_id: str | None = None):
        return _whatsapp_bus.subscribe(scope, last_event_id=last_event_id)


async def _resolve_stream_auth(
    request: Request,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> UUID:
    """Auth dependency for the SSE stream: resolves the caller AND verifies
    ownership of the ``connection_id`` path param via the SAME
    ``_require_record`` scoping every other live op uses — a subscriber must
    never be able to attach to a scope they cannot read. Returns the
    verified ``connection_id`` (handed to ``_stream_scope`` as the resolved
    ``auth_ctx``)."""
    connection_id = UUID(request.path_params["connection_id"])
    user, _token, raw_org = auth
    _require_record(
        store,
        connection_id=connection_id,
        org_id=coerce_org_uuid(raw_org),
        user_id=_coerce_user_uuid(user),
    )
    return connection_id


def _stream_scope(request: Request, connection_id: UUID) -> str:
    return whatsapp_scope(connection_id)


router.include_router(
    create_sse_router(
        _WhatsAppBusProxy(),
        scope_resolver=_stream_scope,
        auth_dependency=_resolve_stream_auth,
        path="/{connection_id}/stream",
    )
)


__all__ = ["router"]
