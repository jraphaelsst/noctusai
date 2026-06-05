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
from typing import Any
from uuid import NAMESPACE_OID, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Response, status

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
    WhatsAppConnectionCreate,
    WhatsAppConnectionOut,
    WhatsAppConnectionQrOut,
    WhatsAppConnectionStatusOut,
    WhatsAppConnectionUpdate,
    WhatsAppWebhookConfigRequest,
    WhatsAppWebhookResultOut,
)
from app.services.credential_vault import CredentialStoreError, EncryptionNotConfigured
from app.services.whatsapp_connection_store import (
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    build_whatsapp_connection_store,
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
    - ``session_name``  — ``sw-<hex6>`` (unique per-connection WAHA session).
                          NEVER reuses "default" so multiple users on the same
                          WAHA server do not collide.
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

    # ── 2. Derive unique session name (multi-account-safe) ─────────────
    session_name = f"sw-{secrets.token_hex(6)}"

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


__all__ = ["router"]
