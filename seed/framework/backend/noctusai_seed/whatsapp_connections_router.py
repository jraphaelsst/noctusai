"""``create_whatsapp_connections_router(...)`` — multi-session, org-scoped
WAHA connection management, ``/api/whatsapp/connections``.

Lifted 2026-09-17 (`community uses social-wiring's mechanisms`, Slice A)
from `social-wiring`'s ``app/routers/whatsapp_connections_router.py`` —
the CRUD + live-WAHA-ops routes only (chat inbox / messages / SSE /
auto-reply toggle are product-specific chatbot-intake concerns and stay
in the product). `social-wiring` is NOT modified in this slice — see
the ``NOC-REMEDIATE[sw-consume-seed-wa-connections]`` marker left at the
top of ``app/services/whatsapp_connection_store.py``.

Supersedes the single-session ``noctusai_seed.whatsapp_admin_router`` —
that router was removed in this same commit (confirmed via a fleet-wide
grep: no product's ``standard_routers=[...]`` ever named
``"whatsapp_admin"``, so nothing regresses; see project history / the
delivery note for the grep evidence).

Exact contract preserved (paths, request/response shapes, status codes)::

    GET    /api/whatsapp/connections               -> list[WhatsAppConnectionOut]
    POST   /api/whatsapp/connections               -> WhatsAppConnectionOut (201)
    PATCH  /api/whatsapp/connections/{id}           -> WhatsAppConnectionOut
    DELETE /api/whatsapp/connections/{id}           -> 204

    GET    /api/whatsapp/connections/{id}/status    -> WhatsAppConnectionStatusOut
    GET    /api/whatsapp/connections/{id}/qr        -> WhatsAppConnectionQrOut
    POST   /api/whatsapp/connections/{id}/start     -> WhatsAppConnectionStatusOut
    POST   /api/whatsapp/connections/{id}/restart   -> WhatsAppConnectionStatusOut
    POST   /api/whatsapp/connections/{id}/logout    -> WhatsAppConnectionStatusOut
    POST   /api/whatsapp/connections/{id}/recover   -> WhatsAppConnectionRecoverOut
    POST   /api/whatsapp/connections/{id}/webhook   -> WhatsAppWebhookResultOut
    PUT    /api/whatsapp/connections/{id}/enabled   -> WhatsAppConnectionOut   (per-app on/off switch)
    POST   /api/whatsapp/connections/{id}/purge     -> WhatsAppPurgeResultOut  (testing-phase erasure; needs ``chat_store_factory``)

**Per-app switch** (``app_enabled``): off => THIS app ignores the line (the inbox webhook stores nothing and
answers ``{"status":"disabled"}``, sends are refused 409 ``app_disabled``). Other apps sharing the WAHA session
own their own webhook entries and keep answering. **Borrowed session** (``session_role='borrower'``): the line
shares another app's WAHA session, so every control that drives the session (start/restart/logout/recover/qr/
webhook) answers 409 ``session_borrowed``. **Purge**: erase the line's conversation data once the app is OFF;
the product's ``on_purge`` seam (leads) runs FIRST, then the chats (messages cascade), and one audit row with
COUNTS ONLY is written. See ``KB § INTEGRATIONS/whatsapp.md § Per-app switch, borrowed sessions and purge``.

CRUD persists via :class:`~noctusai_lib.integrations.whatsapp.
connection_store.WhatsAppConnectionStore` (resolved through the
``store_factory`` DI seam); the live side decrypts the line's API key
just-in-time and drives the seed ``WahaClient``
(``noctusai_lib.integrations.whatsapp.get_whatsapp_client`` by default —
the SAME client the single-session ``whatsapp_admin_router`` used,
here parameterized per line).

**Decoupling.** This module imports NOTHING from ``app.*``. Every
product concern is a constructor kwarg:

- ``store_factory``: zero-arg callable building the store (bind schema
  / table / client / encryption key via ``functools.partial`` around
  ``build_whatsapp_connection_store``). Raising
  ``EncryptionNotConfigured`` maps to a 503 (mirrors `social-wiring`'s
  ``get_connection_store``).
- ``get_current_user_org``: FastAPI dependency resolving
  ``(user, token, org_id)`` — same seam ``create_api_keys_router`` uses.
- ``waha_base_url`` / ``waha_session``: the shared WAHA server config a
  new connection derives its ``base_url`` / ``session_name`` from
  server-side (create accepts ONLY ``label`` + ``api_key`` — everything
  else is derived, exactly as `social-wiring`'s contract v2 states).
- ``resolve_webhook_base_url``: zero-arg callable returning this
  product's own public base URL (bind
  ``noctusai_lib.config.product_urls.resolve_product_url(slug)`` or an
  equivalent) — used to mint the per-connection inbound webhook URL. A
  ``ValueError`` maps to a 503 (mirrors `social-wiring`'s own
  ``resolve_product_url`` failure handling).
- ``waha_client_factory``: DI seam for the per-line WAHA client
  (default: the seed ``get_whatsapp_client``).
- ``resolve_org_id`` / ``resolve_user_id``: coerce whatever shape the
  auth dependency hands back into a ``UUID``. Defaults are generic
  (``UUID(str(x))`` for org; a uuid5-derived fallback for user,
  mirroring `social-wiring`'s own ``_coerce_user_uuid``) — override
  when a product's auth shape needs its own coercion.
- ``webhook_events``: the inbound event set registered on create/
  webhook-config. Defaults to
  :data:`DEFAULT_WHATSAPP_WEBHOOK_EVENTS` (verbatim from
  `social-wiring`'s schema module).
- ``on_session_event``: optional ``async (connection_id, event, payload)
  -> None`` hook fired after ``/recover`` converges — the injectable
  seam for a product's own realtime bus (`social-wiring` publishes to a
  Redis-backed SSE bus here; this module knows nothing about Redis).

Per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B): every product
concern is a constructor kwarg, never a module-level monkeypatch target.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from typing import Any, Awaitable, Callable, Literal, Optional, Sequence
from uuid import NAMESPACE_OID, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.audit.types import AuditActor, AuditEntry
from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
    get_whatsapp_client,
)
from noctusai_lib.security.api_keys import EncryptionNotConfigured

logger = logging.getLogger(__name__)

#: Verbatim from `social-wiring`'s `app/schemas/whatsapp_connection.py`
#: (Migration 040 / Slice 5 — `message.ack` / `message.reaction` feed
#: the realtime bus; `message.any` is WAHA's echo of OUR OWN outbound
#: sends).
DEFAULT_WHATSAPP_WEBHOOK_EVENTS: list[str] = [
    "message",
    "message.any",
    "message.ack",
    "message.reaction",
    "session.status",
]


def _default_resolve_org_id(raw: Any) -> UUID:
    return UUID(str(raw))


def _default_resolve_user_id(user: Any) -> UUID:
    """Resolve the owner UUID from whatever shape the auth dep returned.

    Mirrors `social-wiring`'s ``_coerce_user_uuid``: real Supabase users
    carry a UUID id; local-dev fixtures may use opaque strings — derive
    a stable UUID via uuid5 so the NOT-NULL ``user_id`` column always
    gets a value.
    """
    raw = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return uuid5(NAMESPACE_OID, str(raw))


# ─── wire DTOs (CORE fields only — see module docstring) ──────────────────
class WhatsAppConnectionCreateIn(StrictHttpModel):
    label: str
    api_key: str
    #: ``borrower`` = shares a session another app pairs and drives (test phases); see module docstring.
    session_role: Literal["owner", "borrower"] = "owner"


class WhatsAppConnectionUpdateIn(StrictHttpModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    session_name: Optional[str] = None
    webhook_url: Optional[str] = None


class WhatsAppConnectionOut(StrictHttpModel):
    id: UUID
    label: str
    base_url: str
    session_name: str
    webhook_url: Optional[str] = None
    app_enabled: bool = True
    session_role: str = "owner"
    created_at: Any
    updated_at: Any


class WhatsAppEnabledIn(StrictHttpModel):
    enabled: bool


class WhatsAppPurgeIn(StrictHttpModel):
    #: must equal the connection's label (typed by the admin) -- the same guard as deleting a repository
    confirm: str


class WhatsAppPurgeResultOut(StrictHttpModel):
    connection_id: UUID
    chats_deleted: int
    messages_deleted: int
    #: whatever the product's ``on_purge`` seam reported (e.g. ``leads_deleted`` / ``leads_detached``)
    extra: dict[str, int] = {}


class WhatsAppConnectionStatusOut(StrictHttpModel):
    connection_id: UUID
    status: Optional[str] = None
    paired: bool = False
    me_id: Optional[str] = None
    me_name: Optional[str] = None
    session: str
    error: Optional[str] = None


class WhatsAppConnectionQrOut(StrictHttpModel):
    connection_id: UUID
    scannable: bool
    status: Optional[str] = None
    png_base64: Optional[str] = None


class WhatsAppConnectionRecoverOut(StrictHttpModel):
    connection_id: UUID
    status: Optional[str] = None
    paired: bool = False
    stage: str


class WhatsAppWebhookConfigIn(StrictHttpModel):
    url: str
    events: list[str] = list(DEFAULT_WHATSAPP_WEBHOOK_EVENTS)


class WhatsAppWebhookResultOut(StrictHttpModel):
    connection_id: UUID
    ok: bool
    url: str
    events: list[str]
    status: Optional[str] = None


def _out(record: WhatsAppConnectionRecord) -> WhatsAppConnectionOut:
    return WhatsAppConnectionOut(
        id=record.id,
        label=record.label,
        base_url=record.base_url,
        session_name=record.session_name,
        webhook_url=record.webhook_url,
        app_enabled=record.app_enabled,
        session_role=record.session_role,
        created_at=record.created_at,
        updated_at=record.updated_at,
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


def create_whatsapp_connections_router(
    deps: Any,
    settings: Any,
    *,
    store_factory: Callable[[], WhatsAppConnectionStore],
    get_current_user_org: Callable[..., Any],
    waha_base_url: Optional[str],
    resolve_webhook_base_url: Callable[[], str],
    waha_session: str = "default",
    webhook_path_prefix: str = "/api/whatsapp/webhook",
    webhook_events: Sequence[str] = tuple(DEFAULT_WHATSAPP_WEBHOOK_EVENTS),
    waha_client_factory: Callable[..., Any] = get_whatsapp_client,
    resolve_org_id: Callable[[Any], UUID] = _default_resolve_org_id,
    resolve_user_id: Callable[[Any], UUID] = _default_resolve_user_id,
    on_session_event: Optional[
        Callable[[UUID, str, dict[str, Any]], Awaitable[None]]
    ] = None,
    prefix: str = "/api/whatsapp/connections",
    chat_store_factory: Optional[Callable[[], Any]] = None,
    on_purge: Optional[
        Callable[[UUID, UUID], Awaitable[Optional[dict[str, int]]]]
    ] = None,
    audit_product_slug: str = "",
) -> APIRouter:
    """Build the ``/api/whatsapp/connections`` router.

    ``chat_store_factory`` (a :class:`~noctusai_lib.integrations.whatsapp.inbox.WhatsAppChatStore`) enables the
    ``/purge`` route; ``on_purge(org_id, connection_id) -> {count: n} | None`` is the product seam that erases
    derived data (leads) BEFORE the chats go. ``audit_product_slug`` labels the purge audit row.

    ``deps`` / ``settings`` are accepted (unused directly) for call-site
    symmetry with the other ``noctusai_seed`` router factories — every
    piece this router needs is threaded through explicitly below.
    """
    router = APIRouter(prefix=prefix, tags=["WhatsApp"])
    webhook_events = list(webhook_events)

    def _store_dep() -> WhatsAppConnectionStore:
        try:
            return store_factory()
        except EncryptionNotConfigured as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

    def _require_record(
        store: WhatsAppConnectionStore, *, connection_id: UUID, org_id: UUID, decrypt: bool = False
    ) -> WhatsAppConnectionRecord:
        from noctusai_lib.integrations.whatsapp import WhatsAppConnectionStoreError

        try:
            record = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=decrypt)
        except WhatsAppConnectionStoreError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")
        return record

    def _refuse_borrowed(record: WhatsAppConnectionRecord) -> None:
        """A borrowed session is driven by its owner app: never restart / log out / re-register it from here."""
        if record.session_role == "borrower":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "session_borrowed", "message": "This line borrows another app's WhatsApp session"},
            )

    def _owned_webhook_prefix() -> str:
        """This product's own minted webhook prefix -- the ONLY namespace this router may register/clobber."""
        try:
            base = resolve_webhook_base_url()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cannot build webhook URL: product URL not configured",
            ) from exc
        return f"{base}{webhook_path_prefix}/"

    def _waha_client(record: WhatsAppConnectionRecord):
        return waha_client_factory(
            base_url=record.base_url or None, api_key=record.api_key, session=record.session_name
        )

    # ─── CRUD ───────────────────────────────────────────────────────────
    @router.get("", response_model=list[WhatsAppConnectionOut])
    async def list_connections(
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> list[WhatsAppConnectionOut]:
        _user, _token, raw_org = auth
        records = store.list_connections(org_id=resolve_org_id(raw_org))
        return [_out(r) for r in records]

    @router.post("", response_model=WhatsAppConnectionOut, status_code=status.HTTP_201_CREATED)
    async def create_connection(
        body: WhatsAppConnectionCreateIn,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionOut:
        """Create a new WAHA connection line.

        Accepts ONLY ``label`` + ``api_key``; ``base_url`` / ``session_name`` /
        ``webhook_url`` are derived server-side, exactly as `social-wiring`'s
        contract v2 states.
        """
        user, _token, raw_org = auth

        base_url = (waha_base_url or "").strip()
        if not base_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WAHA server not configured (WAHA_BASE_URL is empty)",
            )
        session_name = (waha_session or "default").strip()

        webhook_token = secrets.token_urlsafe(24)
        try:
            product_base = resolve_webhook_base_url()
        except ValueError as exc:
            logger.error("Cannot resolve product URL for WhatsApp webhook: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cannot build webhook URL: product URL not configured",
            ) from exc
        webhook_url = f"{product_base}{webhook_path_prefix}/{webhook_token}"

        record = store.create_connection(
            org_id=resolve_org_id(raw_org),
            user_id=resolve_user_id(user),
            label=body.label.strip(),
            base_url=base_url,
            api_key=body.api_key.strip(),
            session_name=session_name,
            webhook_url=webhook_url,
            webhook_token=webhook_token,
            session_role=body.session_role,
        )

        client = waha_client_factory(
            base_url=base_url or None, api_key=body.api_key.strip(), session=session_name
        )
        if body.session_role != "borrower":  # a borrowed session is started/paired by its owner
            try:
                await client.start_session()
            except Exception as exc:  # noqa: BLE001 — non-fatal, /start retries later
                logger.warning(
                    "WAHA start_session failed for new connection %s (session=%s): %s",
                    record.id, session_name, exc,
                )
        try:
            # owned_prefix is explicit: never derived from the URL, so only THIS product's entries are replaced.
            await client.set_webhook(
                webhook_url, webhook_events, owned_prefix=f"{product_base}{webhook_path_prefix}/"
            )
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
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
        body: WhatsAppConnectionUpdateIn,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionOut:
        _user, _token, raw_org = auth
        org_id = resolve_org_id(raw_org)
        _require_record(store, connection_id=connection_id, org_id=org_id)
        record = store.update_connection(
            connection_id=connection_id,
            org_id=org_id,
            label=body.label.strip() if body.label is not None else None,
            base_url=body.base_url.strip() if body.base_url is not None else None,
            session_name=body.session_name.strip() if body.session_name is not None else None,
            api_key=body.api_key.strip() if body.api_key is not None else None,
            webhook_url=body.webhook_url if body.webhook_url is not None else None,
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")
        return _out(record)

    @router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_connection(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> Response:
        _user, _token, raw_org = auth
        org_id = resolve_org_id(raw_org)
        # Best-effort WAHA cleanup BEFORE the row (and its api_key) is gone:
        # remove only THIS connection's webhook so a shared session keeps its
        # other products' hooks. Never blocks the delete (204 has no body to
        # carry a warning) but is NOT silent — failures log ERROR. No logout:
        # the paired account belongs to the session, not to this connection.
        try:
            record = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=True)
        except Exception as exc:  # noqa: BLE001 — logged below, delete proceeds
            record = None
            logger.error(
                "WAHA remove_webhook skipped for connection %s: cannot load record: %s",
                connection_id, exc,
            )
        if record is not None and record.webhook_url:
            try:
                await _waha_client(record).remove_webhook(record.webhook_url)
            except Exception as exc:  # noqa: BLE001 — best-effort, logged
                logger.error(
                    "WAHA remove_webhook failed for connection %s (session=%s): %s "
                    "— webhook %s may remain registered on WAHA",
                    connection_id, record.session_name, exc, record.webhook_url,
                )
        deleted = store.delete_connection(connection_id=connection_id, org_id=org_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── Live WAHA ops (per line) ───────────────────────────────────────
    @router.get("/{connection_id}/status", response_model=WhatsAppConnectionStatusOut)
    async def get_connection_status(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionStatusOut:
        _user, _token, raw_org = auth
        record = _require_record(
            store, connection_id=connection_id, org_id=resolve_org_id(raw_org), decrypt=True
        )
        client = _waha_client(record)
        try:
            payload = await client.get_session()
        except Exception as exc:  # noqa: BLE001 — surfaced in DTO, not swallowed
            logger.warning("WAHA status probe failed for line %s: %s", connection_id, exc)
            return WhatsAppConnectionStatusOut(
                connection_id=connection_id, session=record.session_name, error=str(exc)
            )
        return _status_from_session(payload, connection_id=connection_id, session=record.session_name)

    @router.get("/{connection_id}/qr", response_model=WhatsAppConnectionQrOut)
    async def get_connection_qr(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionQrOut:
        _user, _token, raw_org = auth
        record = _require_record(
            store, connection_id=connection_id, org_id=resolve_org_id(raw_org), decrypt=True
        )
        _refuse_borrowed(record)
        client = _waha_client(record)
        try:
            png = await client.get_qr()
        except WahaSessionNotReady as exc:
            return WhatsAppConnectionQrOut(connection_id=connection_id, scannable=False, status=exc.status)
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WAHA QR fetch failed: {exc}"
            ) from exc
        return WhatsAppConnectionQrOut(
            connection_id=connection_id,
            scannable=True,
            status="SCAN_QR_CODE",
            png_base64=base64.b64encode(png).decode("ascii"),
        )

    async def _session_action(*, connection_id: UUID, auth: tuple, store, action: str):
        _user, _token, raw_org = auth
        record = _require_record(
            store, connection_id=connection_id, org_id=resolve_org_id(raw_org), decrypt=True
        )
        _refuse_borrowed(record)
        client = _waha_client(record)
        try:
            await getattr(client, action)()
            payload = await client.get_session()
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WAHA {action} failed: {exc}"
            ) from exc
        return _status_from_session(payload, connection_id=connection_id, session=record.session_name)

    @router.post("/{connection_id}/start", response_model=WhatsAppConnectionStatusOut)
    async def start_connection(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionStatusOut:
        return await _session_action(
            connection_id=connection_id, auth=auth, store=store, action="start_session"
        )

    @router.post("/{connection_id}/restart", response_model=WhatsAppConnectionStatusOut)
    async def restart_connection(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionStatusOut:
        return await _session_action(
            connection_id=connection_id, auth=auth, store=store, action="restart_session"
        )

    @router.post("/{connection_id}/logout", response_model=WhatsAppConnectionStatusOut)
    async def logout_connection(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionStatusOut:
        return await _session_action(
            connection_id=connection_id, auth=auth, store=store, action="logout_session"
        )

    @router.post("/{connection_id}/recover", response_model=WhatsAppConnectionRecoverOut)
    async def recover_connection(
        connection_id: UUID,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionRecoverOut:
        """Run the seed's start->restart->logout+start recovery ladder and
        return the converged session state — mirrors `social-wiring`'s
        own ``/recover`` (the UI's primary reconnect action)."""
        _user, _token, raw_org = auth
        record = _require_record(
            store, connection_id=connection_id, org_id=resolve_org_id(raw_org), decrypt=True
        )
        _refuse_borrowed(record)
        client = _waha_client(record)
        try:
            outcome = await client.recover_session()
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WAHA recover failed: {exc}"
            ) from exc

        if on_session_event is not None:
            await on_session_event(
                connection_id,
                "session.status",
                {
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
        body: WhatsAppWebhookConfigIn,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppWebhookResultOut:
        _user, _token, raw_org = auth
        org_id = resolve_org_id(raw_org)
        record = _require_record(store, connection_id=connection_id, org_id=org_id, decrypt=True)
        _refuse_borrowed(record)
        url = body.url.strip()
        owned = _owned_webhook_prefix()
        if not url.startswith(owned) or len(url) == len(owned):
            # H1: set_webhook REPLACES entries under owned_prefix -- a URL shaped like another app's would
            # delete that app's registration on the shared WAHA session.
            raise HTTPException(
                status_code=422,
                detail={"code": "webhook_url_foreign", "message": "Webhook URL must be under this app's own webhook route"},
            )
        client = _waha_client(record)
        try:
            result = await client.set_webhook(url, body.events, owned_prefix=owned)
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WAHA webhook config failed: {exc}"
            ) from exc
        store.update_connection(connection_id=connection_id, org_id=org_id, webhook_url=url)
        waha_status = result.get("status") if isinstance(result, dict) else None
        return WhatsAppWebhookResultOut(
            connection_id=connection_id, ok=True, url=url, events=body.events, status=waha_status
        )

    # ─── per-app switch ─────────────────────────────────────────────────
    @router.put("/{connection_id}/enabled", response_model=WhatsAppConnectionOut)
    async def set_connection_enabled(
        connection_id: UUID,
        body: WhatsAppEnabledIn,
        auth: tuple = Depends(get_current_user_org),
        store: WhatsAppConnectionStore = Depends(_store_dep),
    ) -> WhatsAppConnectionOut:
        """The app's on/off switch for this line: off => this app ignores its traffic (other apps on the same
        session are unaffected). Idempotent."""
        _user, _token, raw_org = auth
        org_id = resolve_org_id(raw_org)
        _require_record(store, connection_id=connection_id, org_id=org_id)
        record = store.set_app_enabled(connection_id=connection_id, org_id=org_id, enabled=body.enabled)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")
        return _out(record)

    # ─── testing-phase purge ────────────────────────────────────────────
    if chat_store_factory is not None:

        @router.post("/{connection_id}/purge", response_model=WhatsAppPurgeResultOut)
        async def purge_connection_data(
            connection_id: UUID,
            body: WhatsAppPurgeIn,
            request: Request,
            auth: tuple = Depends(get_current_user_org),
            store: WhatsAppConnectionStore = Depends(_store_dep),
        ) -> WhatsAppPurgeResultOut:
            """Erase the line's conversation data (chats + messages + the product's derived data). Only while the
            app switch is OFF and only with the connection label typed back -- irreversible."""
            user, _token, raw_org = auth
            org_id = resolve_org_id(raw_org)
            record = _require_record(store, connection_id=connection_id, org_id=org_id)
            if record.app_enabled:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "app_enabled", "message": "Turn the app OFF for this line before purging"},
                )
            if body.confirm.strip() != record.label:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "confirm_mismatch", "message": "Type the connection label to confirm"},
                )
            extra: dict[str, int] = {}
            if on_purge is not None:  # derived data first: leads reference the chats being erased
                extra = dict(await on_purge(org_id, connection_id) or {})
            chats_deleted, messages_deleted = await asyncio.to_thread(
                chat_store_factory().delete_connection_chats, org_id=org_id, connection_id=connection_id
            )
            await _audit_purge(
                request, user, org_id, connection_id,
                {"chats_deleted": chats_deleted, "messages_deleted": messages_deleted, **extra},
            )
            return WhatsAppPurgeResultOut(
                connection_id=connection_id,
                chats_deleted=chats_deleted,
                messages_deleted=messages_deleted,
                extra=extra,
            )

    async def _audit_purge(
        request: Request, user: Any, org_id: UUID, connection_id: UUID, counts: dict[str, int]
    ) -> None:
        """One audit row, COUNTS ONLY (no label, number or message text). Skipped -- loudly logged -- when the
        app has no audit sink wired."""
        logger.warning("whatsapp.purge connection=%s org=%s counts=%s", connection_id, org_id, counts)
        sink = getattr(request.app.state, "audit_sink", None)
        if sink is None or not getattr(request.app.state, "audit_enabled", False):
            return
        await sink.record(AuditEntry(
            product_slug=audit_product_slug,
            method="POST",
            route_template=f"{prefix}/{{connection_id}}/purge",
            path_params={"connection_id": str(connection_id), **counts},
            status=200,
            actor_kind="user",
            client_hint="whatsapp-purge",
            actor=AuditActor(user_id=str(resolve_user_id(user)), org_id=str(org_id), role="admin"),
        ))

    return router
