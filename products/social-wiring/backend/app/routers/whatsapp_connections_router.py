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
    POST   /api/whatsapp/connections/{id}/webhook → wire the inbound webhook

CRUD persists to ``social_wiring.whatsapp_connections`` via the
:class:`WhatsAppConnectionStore` (resolved through the ``get_connection_store``
DI seam); the live side decrypts the line's API key just-in-time and drives
the seed ``WahaClient`` (the same client the single-session seed
``whatsapp_admin_router`` uses, here parameterized per line through the
``get_waha_client_factory`` DI seam).

Auth: ``Depends(get_current_user_org)`` → ``(user, token, org_id)``; every
store call additionally scopes by the resolved ``user_id`` so lines are
isolated per user (the canonical pattern — see
``KB § PATTERNS/backend.md § Auth — canonical pattern``). DI seams over
patching per ``KB § PATTERNS/di-test-seam.md``.
"""
from __future__ import annotations

import base64
import logging
import secrets
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_OID, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    get_whatsapp_client,
)

from app.config import SocialWiringSettings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_settings,
)
from app.schemas.whatsapp_connection import (
    AutoReplyToggleOut,
    AutoReplyToggleRequest,
    ChatSummary,
    MessageOut,
    SendMessageRequest,
    WhatsAppConnectionApiKeyOut,
    WhatsAppConnectionCreate,
    WhatsAppConnectionOut,
    WhatsAppConnectionQrOut,
    WhatsAppConnectionStatusOut,
    WhatsAppConnectionUpdate,
    WhatsAppWebhookConfigRequest,
    WhatsAppWebhookResultOut,
)
from app.modules.email_marketing.services.contact_service import ContactService
from app.services.credential_vault import CredentialStoreError, EncryptionNotConfigured
from app.services.message_store import MessageStore
from app.services.whatsapp_connection_store import (
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    build_whatsapp_connection_store,
)
from app.services.whatsapp_identity import ResolvedIdentity, build_lids_map_from_list

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
) -> list[WhatsAppConnectionOut]:
    user, _token, raw_org = auth
    records = store.list_connections(
        org_id=coerce_org_uuid(raw_org), user_id=_coerce_user_uuid(user)
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
        await client.set_webhook(webhook_url, ["message", "session.status"])
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

    record = store.update_connection(
        connection_id=connection_id,
        org_id=org_id,
        user_id=user_id,
        label=body.label.strip() if body.label is not None else None,
        base_url=body.base_url.strip() if body.base_url is not None else None,
        session_name=body.session_name.strip() if body.session_name is not None else None,
        api_key=body.api_key.strip() if body.api_key is not None else None,
        webhook_url=body.webhook_url if body.webhook_url is not None else None,
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


def _waha_chat_to_summary(
    waha_chat: dict[str, Any],
    *,
    canonical_chat_id: str | None = None,
    contact_display: str | None = None,
    contact_id: str | None = None,
) -> dict[str, Any] | None:
    """Map a WAHA chat object to a ``ChatSummary``-shaped dict.

    WAHA NOWEB chat shape (observed):
        {"id": {"_serialized": "5511@c.us", ...}, "name": "Alice",
         "lastMessage": {"body": "hi", "fromMe": false, "timestamp": 1718000000}}

    ``canonical_chat_id``: when supplied (from identity dedup), this overrides
    the raw JID from WAHA — the caller has already resolved the canonical phone-JID.

    ``contact_display``: resolved display name (contacts table → WAHA name →
    phone digits → raw LID) when supplied by the caller.

    ``contact_id``: contacts.id UUID when the human is registered.

    ``last_message_at`` is ``None`` (not "") when there is no usable timestamp
    so the FE never renders "Invalid Date".

    Returns ``None`` when the shape is unrecognisable (defensive — never 500).
    """
    try:
        raw_id = waha_chat.get("id") or {}
        raw_chat_id: str = raw_id if isinstance(raw_id, str) else raw_id.get("_serialized") or ""
        if not raw_chat_id:
            return None
        chat_id = canonical_chat_id or raw_chat_id
        waha_name: str = waha_chat.get("name") or waha_chat.get("pushName") or ""
        if contact_display:
            contact: str = contact_display
        else:
            contact = waha_name or (
                raw_chat_id
                .replace("@c.us", "")
                .replace("@s.whatsapp.net", "")
                .replace("@lid", "")
            )
        last_msg = waha_chat.get("lastMessage") or {}
        body: str = last_msg.get("body") or ""
        ts_raw = last_msg.get("timestamp")  # Unix epoch seconds (int) from WAHA
        last_message_at: str | None
        if ts_raw:
            from datetime import timezone  # noqa: PLC0415 — lazy import, not on hot path
            last_message_at = datetime.fromtimestamp(
                int(ts_raw), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        else:
            last_message_at = None  # FE guards on null; never emit ""
        from_me: bool = bool(last_msg.get("fromMe"))
        return {
            "chat_id": chat_id,
            "contact": contact,
            "contact_id": contact_id,
            "last_message": body,
            "last_message_at": last_message_at,
            "last_direction": "outbound" if from_me else "inbound",
            "unread": 0,  # WAHA provides unreadCount on some engines; default to 0
        }
    except Exception:  # noqa: BLE001 — defensive; malformed WAHA payload never crashes
        return None


def _waha_message_to_out(
    waha_msg: dict[str, Any], *, chat_id: str
) -> dict[str, Any] | None:
    """Map a WAHA message object to a ``MessageOut``-shaped dict.

    WAHA NOWEB message shape (observed):
        {"id": {"_serialized": "...", "id": "BAE5..."}, "body": "hi",
         "from": "5511@c.us", "timestamp": 1718000000, "fromMe": false}

    Returns ``None`` when the shape is unrecognisable.
    """
    try:
        from datetime import timezone  # noqa: PLC0415 — lazy import
        msg_id_raw = waha_msg.get("id") or {}
        provider_message_id: str | None = (
            msg_id_raw.get("_serialized")
            if isinstance(msg_id_raw, dict)
            else (str(msg_id_raw) if msg_id_raw else None)
        )
        body: str = waha_msg.get("body") or ""
        ts_raw = waha_msg.get("timestamp")
        if ts_raw:
            created_at = datetime.fromtimestamp(
                int(ts_raw), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        else:
            created_at = ""
        from_me: bool = bool(waha_msg.get("fromMe"))
        direction = "outbound" if from_me else "inbound"
        # Deterministic synthetic id: use provider id or a hash of (chat_id, ts, dir)
        import hashlib  # noqa: PLC0415
        row_id = provider_message_id or hashlib.sha1(  # noqa: S324 — not security-critical
            f"{chat_id}:{ts_raw}:{direction}:{body[:32]}".encode()
        ).hexdigest()[:16]
        return {
            "id": row_id,
            "chat_id": chat_id,
            "direction": direction,
            "body": body,
            "created_at": created_at,
            "provider_message_id": provider_message_id,
            "structured_payload": None,
        }
    except Exception:  # noqa: BLE001 — defensive
        return None


@router.get("/{connection_id}/chats", response_model=list[ChatSummary])
async def list_chats(
    connection_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    msg_store_factory: Any = Depends(get_message_store_factory),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> list[ChatSummary]:
    """List all contacts that have exchanged messages on this connection.

    Merges WAHA live chat list (requires NOWEB store) with persisted
    ``conversation_messages``.  When WAHA returns 400 (store not enabled)
    or any other error, falls back to DB-only results — never 500.

    Identity dedup: builds a ONE-SHOT LID→phone map from WAHA ``list_lids()``
    so that multiple JID forms of the same human collapse into one ChatSummary
    (canonical chat_id = ``<phone>@c.us``; no N-per-chat WAHA calls).

    Contact lookup: checks social_wiring.contacts for a registered record
    per resolved phone to surface the stored nome and contact_id UUID.

    Returns ``ChatSummary[]`` ordered by last_message_at DESC (null-last).
    Empty list (no messages yet) is 200 + [].
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    record = _require_record(
        store, connection_id=connection_id, org_id=org_id, user_id=user_id, decrypt=True
    )

    msg_store: MessageStore = msg_store_factory(org_id)
    db_rows = msg_store.list_chats(connection_id=connection_id)

    # ── Build per-org contacts index (phone → {nome, id}) ────────────────────
    # We need this regardless of whether WAHA is available.
    contact_svc = ContactService(db=get_admin_client(), org_id=str(org_id))
    all_contacts, _ = contact_svc.list_contacts(page=1, page_size=500)
    # phone → {nome, contact_id}
    phone_to_contact: dict[str, dict[str, Any]] = {}
    for c in all_contacts:
        wp = c.get("whatsapp_phone")
        if wp:
            phone_to_contact[wp] = {"nome": c.get("nome"), "contact_id": str(c["id"])}

    # ── Attempt to build LID→phone map from WAHA ─────────────────────────────
    lids_phone_map: dict[str, str] = {}  # lid_jid → phone_digits
    try:
        client = _waha_client(record, waha_factory)
        lids_list = await client.list_lids()
        lids_phone_map = build_lids_map_from_list(lids_list)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "WAHA list_lids unavailable for connection %s — identity dedup disabled: %s",
            connection_id, exc,
        )
        # client may be partially built; reset so we don't try again below
        client = None  # type: ignore[assignment]

    def _canonical_phone(raw_jid: str) -> str | None:
        """Resolve any JID to phone digits, or None when unknown."""
        from noctusai_lib.integrations.whatsapp.lid_auth import (  # noqa: PLC0415
            is_lid,
            normalize_phone,
        )
        if raw_jid.endswith("@lid"):
            return lids_phone_map.get(raw_jid)
        if raw_jid.endswith(("@c.us", "@s.whatsapp.net")):
            return normalize_phone(raw_jid)
        return None

    def _resolve_contact_info(phone: str | None) -> tuple[str | None, str | None]:
        """Return (nome, contact_id) for a resolved phone, or (None, None)."""
        if not phone:
            return None, None
        entry = phone_to_contact.get(phone)
        if not entry:
            return None, None
        return entry.get("nome"), entry.get("contact_id")

    # ── Index DB rows using canonical phone as key ────────────────────────────
    # DB rows keyed by raw_sender (JID as stored); remap to canonical chat_id.
    by_canonical: dict[str, dict[str, Any]] = {}
    for r in db_rows:
        raw_cid = r["chat_id"]
        phone = _canonical_phone(raw_cid)
        canonical = f"{phone}@c.us" if phone else raw_cid
        nome, cid = _resolve_contact_info(phone)
        row = {
            **r,
            "chat_id": canonical,
            "contact": nome or r.get("contact") or (phone or raw_cid),
            "contact_id": cid,
        }
        if canonical not in by_canonical:
            by_canonical[canonical] = row
        else:
            # Merge: keep latest last_message_at, add unread counts
            existing = by_canonical[canonical]
            existing_ts = existing.get("last_message_at") or ""
            new_ts = row.get("last_message_at") or ""
            if new_ts > existing_ts:
                by_canonical[canonical] = {
                    **row,
                    "unread": existing.get("unread", 0) + row.get("unread", 0),
                }
            else:
                existing["unread"] = existing.get("unread", 0) + row.get("unread", 0)

    # ── Attempt to merge WAHA live chat list ─────────────────────────────────
    try:
        if client is None:
            client = _waha_client(record, waha_factory)
        waha_chats = await client.list_chats()
        for wc in waha_chats:
            raw_id_obj = wc.get("id") or {}
            raw_cid = raw_id_obj if isinstance(raw_id_obj, str) else (
                raw_id_obj.get("_serialized") or ""
            )
            if not raw_cid:
                continue
            phone = _canonical_phone(raw_cid)
            canonical = f"{phone}@c.us" if phone else raw_cid
            nome, contact_id_val = _resolve_contact_info(phone)
            waha_name = wc.get("name") or wc.get("pushName") or ""
            display = nome or waha_name or (phone or raw_cid.split("@")[0])
            summary = _waha_chat_to_summary(
                wc,
                canonical_chat_id=canonical,
                contact_display=display,
                contact_id=contact_id_val,
            )
            if summary is None:
                continue
            if canonical not in by_canonical:
                by_canonical[canonical] = summary
            else:
                db_entry = by_canonical[canonical]
                waha_ts = summary.get("last_message_at") or ""
                db_ts = db_entry.get("last_message_at") or ""
                if waha_ts > db_ts:
                    by_canonical[canonical] = {
                        **summary,
                        "unread": db_entry.get("unread", 0),
                    }
                # Prefer registered contact info when available
                if db_entry.get("contact_id") and not by_canonical[canonical].get("contact_id"):
                    by_canonical[canonical]["contact_id"] = db_entry["contact_id"]
                if not _is_phone_like_display(by_canonical[canonical].get("contact") or ""):
                    pass  # keep the better name already there
                elif nome:
                    by_canonical[canonical]["contact"] = nome
    except Exception as exc:  # noqa: BLE001 — graceful fallback; not a 500
        logger.warning(
            "WAHA list_chats unavailable for connection %s — falling back to DB only: %s",
            connection_id, exc,
        )

    merged = sorted(
        by_canonical.values(),
        key=lambda s: s.get("last_message_at") or "",
        reverse=True,
    )
    return [ChatSummary(**r) for r in merged]


def _is_phone_like_display(display: str) -> bool:
    """True when display is just digits/JID — a real name is better."""
    import re  # noqa: PLC0415
    return bool(re.match(r"^[\d+@.\-\s]+$", display))


@router.get("/{connection_id}/chats/{chat_id:path}/messages", response_model=list[MessageOut])
async def list_messages(
    connection_id: UUID,
    chat_id: str,
    limit: int = 50,
    before: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    msg_store_factory: Any = Depends(get_message_store_factory),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> list[MessageOut]:
    """List messages for one chat thread (raw_sender = chatId), oldest-first.

    Merges WAHA history (requires NOWEB store) with persisted
    ``conversation_messages``.  Deduplicates by ``provider_message_id``
    when available; falls back to ``(direction, body[:32], created_at)``
    fingerprint.  When WAHA is unavailable, falls back to DB-only.

    ``before`` is an ISO 8601 UTC cursor — when set, only messages with
    created_at < before are returned (page-backwards).
    Non-owner / unknown connection → 404.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    user_id = _coerce_user_uuid(user)
    actual_limit = min(limit, 200)
    record = _require_record(
        store, connection_id=connection_id, org_id=org_id, user_id=user_id, decrypt=True
    )

    # ── Expand the requested chat_id to ALL its JID aliases ──────────────────
    # chat_id from the FE is the canonical <phone>@c.us.  WAHA stored messages
    # may be keyed as @c.us, @s.whatsapp.net, or @lid.  Expand so DB + WAHA
    # queries cover all aliases.
    from noctusai_lib.integrations.whatsapp.lid_auth import (  # noqa: PLC0415
        normalize_phone,
    )
    jid_aliases: list[str] = [chat_id]
    try:
        client_for_lids = _waha_client(record, waha_factory)
        lids_list = await client_for_lids.list_lids()
        lids_map = build_lids_map_from_list(lids_list)
        # phone digits from the requested canonical JID
        phone_digits = normalize_phone(chat_id)
        jid_aliases = [
            f"{phone_digits}@c.us",
            f"{phone_digits}@s.whatsapp.net",
        ]
        # add all @lid JIDs that map to this phone
        for lid_jid, pdigits in lids_map.items():
            if pdigits == phone_digits:
                jid_aliases.append(lid_jid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "JID alias expansion failed for chat %s connection %s — using raw JID: %s",
            chat_id, connection_id, exc,
        )
        client_for_lids = None  # type: ignore[assignment]

    msg_store: MessageStore = msg_store_factory(org_id)
    # Query DB for all aliases to get full history across JID forms
    db_rows: list[dict[str, Any]] = []
    seen_aliases: set[str] = set()
    for alias in jid_aliases:
        if alias in seen_aliases:
            continue
        seen_aliases.add(alias)
        rows = msg_store.list_messages(
            connection_id=connection_id,
            raw_sender=alias,
            limit=actual_limit,
            before=before,
        )
        db_rows.extend(rows)

    # ── Dedup key ─────────────────────────────────────────────────────────────
    def _dedup_key(row: dict[str, Any]) -> str:
        pmid = row.get("provider_message_id")
        if pmid:
            return f"pmid:{pmid}"
        return f"fp:{row.get('direction')}:{(row.get('body') or '')[:32]}:{row.get('created_at')}"

    seen_keys: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in db_rows:
        k = _dedup_key(row)
        if k not in seen_keys:
            seen_keys.add(k)
            merged.append({**row, "chat_id": chat_id})  # normalise to canonical JID

    # ── Attempt to merge WAHA message history across all aliases ─────────────
    try:
        waha_client_ref = client_for_lids if client_for_lids is not None else _waha_client(record, waha_factory)
        for alias in jid_aliases:
            try:
                waha_msgs = await waha_client_ref.fetch_chat_messages(alias, limit=actual_limit)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "WAHA fetch_chat_messages failed for alias %s connection %s: %s",
                    alias, connection_id, exc,
                )
                continue
            for wm in waha_msgs:
                mapped = _waha_message_to_out(wm, chat_id=chat_id)
                if mapped is None:
                    continue
                if before and (mapped.get("created_at") or "") >= before:
                    continue
                k = _dedup_key(mapped)
                if k not in seen_keys:
                    seen_keys.add(k)
                    merged.append(mapped)
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        logger.warning(
            "WAHA message fetch unavailable for connection %s chat %s — "
            "falling back to DB only: %s",
            connection_id, chat_id, exc,
        )

    # Sort oldest-first, cap at limit.
    merged.sort(key=lambda m: m.get("created_at") or "")
    merged = merged[:actual_limit]
    return [MessageOut(**r) for r in merged]


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


__all__ = ["router"]
