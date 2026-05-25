"""
Shared WhatsApp connection-admin router — `/api/whatsapp/connection`.

Surfaces the WAHA session lifecycle (status, QR pairing, restart, logout,
webhook wiring) so products with a WhatsApp chatbot can manage the
connection from their own UI instead of curl + the WAHA dashboard.

Endpoints:
    GET  /api/whatsapp/connection           → ConnectionStatusDTO
    GET  /api/whatsapp/connection/qr        → image/png  (409 JSON when paired)
    POST /api/whatsapp/connection/restart   → ConnectionStatusDTO
    POST /api/whatsapp/connection/logout    → ConnectionStatusDTO
    POST /api/whatsapp/connection/webhook   → WebhookResult

Backing client: ``get_whatsapp_client(base_url=, api_key=, session=)`` —
returns the real ``WahaClient`` when ``waha_base_url`` is set, else
``FakeWahaClient`` (deterministic, in-memory). Both satisfy the
``WahaSessionAdmin`` Protocol.

Auth: any authenticated user (`deps.get_current_user(authorization)`-shaped),
matching the sibling `scheduler` / `team` standard routers. WAHA session
state is infrastructure state, not per-user data — no per-org filtering.

Products opt in via ``create_product_app(standard_routers=["whatsapp_admin", ...])``.
Config is read off the product settings object: ``waha_base_url``,
``waha_api_key``, ``waha_session`` (optional ``waha_webhook_url`` default).
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from noctusai_lib.integrations.whatsapp import (
    WahaSessionNotReady,
    get_whatsapp_client,
)

logger = logging.getLogger(__name__)


class ConnectionStatusDTO(BaseModel):
    """Boundary DTO for the WAHA session — no raw WAHA envelope leaks."""

    configured: bool = Field(
        ..., description="True when waha_base_url is set (real client)."
    )
    status: Optional[str] = Field(
        default=None,
        description="WAHA session status (WORKING / SCAN_QR_CODE / STARTING / …).",
    )
    paired: bool = Field(
        default=False, description="True when a WhatsApp account is linked."
    )
    me_id: Optional[str] = Field(
        default=None, description="Linked account chat id, when paired."
    )
    me_name: Optional[str] = Field(
        default=None, description="Linked account push name, when paired."
    )
    session: str = Field(..., description="WAHA session name.")
    error: Optional[str] = Field(
        default=None, description="Set when the status probe failed."
    )


class QrDTO(BaseModel):
    """QR pairing payload.

    Always 200 so a polling UI has one stable contract: `scannable`
    flips false→true→false across the pairing lifecycle. `png_base64`
    is a ready-to-render data-URI body (`<img src="data:image/png;
    base64,{png_base64}">`) — JSON, not a binary stream, so it rides
    the authenticated API client like every other endpoint.
    """

    scannable: bool = Field(
        ..., description="True when a QR is available to scan."
    )
    status: Optional[str] = Field(
        default=None, description="WAHA session status."
    )
    png_base64: Optional[str] = Field(
        default=None, description="Base64 PNG when scannable, else null."
    )


class WebhookConfigRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    events: list[str] = Field(
        default_factory=lambda: ["message", "message.any", "session.status"]
    )


class WebhookResult(BaseModel):
    ok: bool
    url: str
    events: list[str]
    status: Optional[str] = None


def _dto_from_session(
    payload: dict[str, Any], *, configured: bool, session: str
) -> ConnectionStatusDTO:
    status = payload.get("status")
    me = payload.get("me") if isinstance(payload.get("me"), dict) else None
    return ConnectionStatusDTO(
        configured=configured,
        status=status,
        paired=bool(me) and status == "WORKING",
        me_id=(me or {}).get("id"),
        me_name=(me or {}).get("pushName"),
        session=session,
    )


def create_whatsapp_admin_router(deps, settings) -> APIRouter:
    """Build the `/api/whatsapp/connection` router.

    `deps` supplies the auth gate; `settings` supplies WAHA config. Read
    via getattr so a product opting in without the attrs fails loudly at
    request time with a clear message, not at import.
    """
    router = APIRouter(prefix="/api/whatsapp/connection", tags=["WhatsApp"])

    def _client():
        base_url = getattr(settings, "waha_base_url", None)
        api_key = getattr(settings, "waha_api_key", None)
        session = getattr(settings, "waha_session", "default")
        return (
            get_whatsapp_client(
                base_url=base_url, api_key=api_key, session=session
            ),
            bool(base_url),
            session,
        )

    @router.get("", response_model=ConnectionStatusDTO)
    async def get_connection(
        authorization: Optional[str] = Header(None),
    ) -> ConnectionStatusDTO:
        await deps.get_current_user(authorization)
        client, configured, session = _client()
        try:
            payload = await client.get_session()
        except Exception as exc:  # noqa: BLE001 — surfaced in DTO, not swallowed
            logger.warning("WAHA session probe failed: %s", exc)
            return ConnectionStatusDTO(
                configured=configured, session=session, error=str(exc)
            )
        return _dto_from_session(
            payload, configured=configured, session=session
        )

    @router.get("/qr", response_model=QrDTO)
    async def get_qr(authorization: Optional[str] = Header(None)) -> QrDTO:
        await deps.get_current_user(authorization)
        client, _configured, _session = _client()
        try:
            png = await client.get_qr()
        except WahaSessionNotReady as exc:
            # Expected control-flow, not an error: the session is paired
            # or starting, so there is nothing to scan right now. 200 so
            # a polling UI keeps one contract instead of branching on 409.
            return QrDTO(scannable=False, status=exc.status, png_base64=None)
        return QrDTO(
            scannable=True,
            status="SCAN_QR_CODE",
            png_base64=base64.b64encode(png).decode("ascii"),
        )

    @router.post("/restart", response_model=ConnectionStatusDTO)
    async def restart(
        authorization: Optional[str] = Header(None),
    ) -> ConnectionStatusDTO:
        await deps.get_current_user(authorization)
        client, configured, session = _client()
        await client.restart_session()
        payload = await client.get_session()
        return _dto_from_session(
            payload, configured=configured, session=session
        )

    @router.post("/logout", response_model=ConnectionStatusDTO)
    async def logout(
        authorization: Optional[str] = Header(None),
    ) -> ConnectionStatusDTO:
        await deps.get_current_user(authorization)
        client, configured, session = _client()
        await client.logout_session()
        payload = await client.get_session()
        return _dto_from_session(
            payload, configured=configured, session=session
        )

    @router.post("/webhook", response_model=WebhookResult)
    async def configure_webhook(
        body: WebhookConfigRequest,
        authorization: Optional[str] = Header(None),
    ) -> WebhookResult:
        await deps.get_current_user(authorization)
        client, _configured, _session = _client()
        result = await client.set_webhook(body.url, body.events)
        status = result.get("status") if isinstance(result, dict) else None
        return WebhookResult(
            ok=True, url=body.url, events=body.events, status=status
        )

    return router
