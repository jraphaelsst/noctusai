"""Product-only bridge for the ``agents`` control plane's One Chat toggle
(SW1, ``project-history/roadmaps/julia-agents-academia-2026-09.md``,
contract §E.6) — a NEW route pair. The existing JWT-authenticated
``PUT /api/whatsapp/connections/{id}/auto-reply`` route
(``whatsapp_connections_router.py:1150``) is byte-identical, untouched.
No prompt, tool, sender-policy or webhook behaviour changes anywhere in
social-wiring.

**Auth.** ``get_auth_context`` (this product's unified dep,
``app.dependencies``) composed with the seed's
``require_scopes(..., restrict="product_only")`` dependency factory:

  - Missing / invalid / expired credential → ``401`` (raised by the
    underlying ``get_auth_context`` dep itself, before ``require_scopes``
    or this router's body ever run).
  - ``caller_kind != "product"`` (a human SSO session) → ``403
    product_required`` — a user session must never pass through this
    bridge (contract §E.6). Enforced by ``require_scopes``'s own
    ``restrict="product_only"`` branch, ahead of the scope check.
  - Missing scope → ``403 scope_missing`` (``require_scopes``).
  - ``ctx.issuer != "agents"`` → ``403 issuer_not_allowed``. Narrower
    than the scope check alone (a scope string says WHAT a token may
    do, never WHO holds it) — checked in THIS router's body, since
    ``require_scopes`` has no issuer concept. Any other product-token
    holder minted with the SAME scope string must not reach this
    bridge.
  - Unknown connection, or one belonging to another org → ``404``
    (``WhatsAppConnectionStore.get_connection`` is already ORG-scoped;
    a cross-org id simply doesn't match, same shape as every other
    connection-scoped route in this product).

**Write path.** Calls the SAME
``WhatsAppConnectionStore.update_auto_reply`` the JWT route uses — no
parallel write path, no drift between the two callers' views of
``auto_reply_enabled``. Reuses the JWT route's own
``AutoReplyToggleRequest`` / ``AutoReplyToggleOut`` schemas
(``app/schemas/whatsapp_connection.py``) and its ``get_connection_store``
DI seam (``whatsapp_connections_router.py``) — same 503 config-gap
mapping, same test-override seam.

**Unaudited today.** Contract §E.6 calls for "an audit row is written"
per resolved product-token call; the seed's
``noctusai_lib.api.auth.session.audit.ApiTokenAuditWriter`` ships the
writer but its own module docstring defers wiring to ASGI middleware
(the RESPONSE status code is only known after the handler runs, not at
a plain ``Depends(...)`` site) — that middleware, and this router's
opt-in to it, is a LATER slice's scope (SW1's dispatch brief says so
explicitly). This bridge writes no audit row until then.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from noctusai_lib.api.auth.session import AuthContext, require_scopes

from app.dependencies import get_auth_context
from app.routers.whatsapp_connections_router import get_connection_store
from app.schemas.whatsapp_connection import AutoReplyToggleOut, AutoReplyToggleRequest
from app.services.credential_vault import CredentialStoreError
from app.services.whatsapp_connection_store import WhatsAppConnectionStore

router = APIRouter(prefix="/api/agents-bridge/one-chat", tags=["Agents Bridge"])


class OneChatStateOut(BaseModel):
    """``GET /api/agents-bridge/one-chat/{connection_id}`` response
    (contract §E.6). Deliberately narrower than the JWT route's
    ``WhatsAppConnectionOut`` — the bridge exposes only what the
    ``agents`` product's ``estado_externo`` projection (contract §E.2)
    needs, never the connection's WAHA credentials or intake config."""

    connection_id: UUID
    label: str
    auto_reply_enabled: bool


_READ_SCOPE = "social-wiring:one-chat:read"
_TOGGLE_SCOPE = "social-wiring:one-chat:toggle"
_ISSUER = "agents"


def _require_read(
    ctx: AuthContext = Depends(
        require_scopes(
            _READ_SCOPE,
            get_auth_context=get_auth_context,
            restrict="product_only",
        )
    ),
) -> AuthContext:
    if ctx.issuer != _ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Token issuer not allowed for this bridge",
                "code": "issuer_not_allowed",
            },
        )
    return ctx


def _require_toggle(
    ctx: AuthContext = Depends(
        require_scopes(
            _TOGGLE_SCOPE,
            get_auth_context=get_auth_context,
            restrict="product_only",
        )
    ),
) -> AuthContext:
    if ctx.issuer != _ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Token issuer not allowed for this bridge",
                "code": "issuer_not_allowed",
            },
        )
    return ctx


def _require_connection(
    store: WhatsAppConnectionStore, *, connection_id: UUID, org_id: UUID
):
    """Fetch a line ORG-scoped or 404 — mirrors
    ``whatsapp_connections_router._require_record`` (kept local rather
    than importing that module-private helper, same shape)."""
    try:
        record = store.get_connection(
            connection_id=connection_id, org_id=org_id, decrypt=False
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


@router.get("/{connection_id}", response_model=OneChatStateOut)
async def get_one_chat_state(
    connection_id: UUID,
    ctx: AuthContext = Depends(_require_read),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> OneChatStateOut:
    """The ``agents`` product's live read of a One Chat connection's
    label + auto-reply gate (contract §E.2's ``estado_externo``)."""
    record = _require_connection(store, connection_id=connection_id, org_id=ctx.org_id)
    return OneChatStateOut(
        connection_id=record.id,
        label=record.label,
        auto_reply_enabled=record.auto_reply_enabled,
    )


@router.put("/{connection_id}/auto-reply", response_model=AutoReplyToggleOut)
async def toggle_one_chat_auto_reply(
    connection_id: UUID,
    body: AutoReplyToggleRequest,
    ctx: AuthContext = Depends(_require_toggle),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> AutoReplyToggleOut:
    """Toggle One Chat's auto-reply gate on behalf of the ``agents``
    product (contract §E.2's ``POST /api/agents/one-chat/toggle``
    upstream call). Calls the SAME
    ``WhatsAppConnectionStore.update_auto_reply`` the JWT route uses."""
    _require_connection(store, connection_id=connection_id, org_id=ctx.org_id)

    record = store.update_auto_reply(
        connection_id=connection_id,
        org_id=ctx.org_id,
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
