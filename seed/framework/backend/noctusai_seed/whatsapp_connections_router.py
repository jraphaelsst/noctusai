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

import base64
import logging
import secrets
from typing import Any, Awaitable, Callable, Optional, Sequence
from uuid import NAMESPACE_OID, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Response, status

from noctusai_lib.api import StrictHttpModel
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
    created_at: Any
    updated_at: Any


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
) -> APIRouter:
    """Build the ``/api/whatsapp/connections`` router.

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
        )

        client = waha_client_factory(
            base_url=base_url or None, api_key=body.api_key.strip(), session=session_name
        )
        try:
            await client.start_session()
        except Exception as exc:  # noqa: BLE001 — non-fatal, /start retries later
            logger.warning(
                "WAHA start_session failed for new connection %s (session=%s): %s",
                record.id, session_name, exc,
            )
        try:
            await client.set_webhook(webhook_url, webhook_events)
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
        deleted = store.delete_connection(connection_id=connection_id, org_id=resolve_org_id(raw_org))
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
        client = _waha_client(record)
        url = body.url.strip()
        try:
            result = await client.set_webhook(url, body.events)
        except Exception as exc:  # noqa: BLE001 — explicit action, surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WAHA webhook config failed: {exc}"
            ) from exc
        store.update_connection(connection_id=connection_id, org_id=org_id, webhook_url=url)
        waha_status = result.get("status") if isinstance(result, dict) else None
        return WhatsAppWebhookResultOut(
            connection_id=connection_id, ok=True, url=url, events=body.events, status=waha_status
        )

    return router
