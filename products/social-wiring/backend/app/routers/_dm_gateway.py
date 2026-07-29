"""Instagram Direct — one gateway over the two Meta messaging models.

An ``integration_accounts`` row is EITHER model, and which one it is decides
the whole call shape:

| | Facebook-Login (``provider="meta"``) | Instagram-Login (``provider="instagram"``) |
|---|---|---|
| Adapter | ``MetaOAuthAdapter`` | ``InstagramLoginOAuthAdapter`` |
| Host | ``graph.facebook.com`` | ``graph.instagram.com`` |
| Token | Page access token | IG **User** access token |
| Conversations node | ``/{PAGE-ID}/conversations`` | ``/me/conversations`` |
| "Who am I" | the IG account behind the Page | ``/me`` |
| Page lookup per call | yes | none — there is no Page |

Roadmap ``ig-login-messaging-migration-2026-07`` S3 is exactly this file. S1
built the Instagram-Login adapter and S2 stored the accounts, but nothing ever
routed to it — the DMs router only spoke the Facebook-Login shape, so an
IG-Login account connected through S2's OAuth was unreachable dead weight.

**Why a gateway and not an `if` in each route.** All three DM routes need
self-id + a per-model call, and the Page lookup exists in one model only.
Inline, that is the same branch written three times, and the next route makes
it four. Here the router asks for ``self_id`` / ``list_conversations`` /
``list_messages`` / ``send`` and never learns which model answered.

**Why router-layer and not `app/services/`.** The Facebook-Login path needs
``resolve_primary_ig_account`` / ``resolve_primary_ig_page_id``, which raise
``HTTPException`` — HTTP semantics belong on this side of the line. The
credential + model resolution proper lives in
``app.services.meta.get_dm_adapter_for_account``; this module only wraps
whichever adapter that returns.
"""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from noctusai_lib.integrations.meta.types import Conversation, DirectMessage

from app.routers._meta_common import (
    resolve_primary_ig_account,
    resolve_primary_ig_page_id,
)
from app.services.meta import get_dm_adapter_for_account

__all__ = [
    "DmGateway",
    "FacebookLoginDmGateway",
    "InstagramLoginDmGateway",
    "build_dm_gateway",
    "gateway_for",
]


class DmGateway(Protocol):
    """Model-agnostic IG Direct contract the DMs router consumes.

    ``self_id`` is the IG account's own id — the router compares it against a
    message's ``sender_id`` to derive inbound/outbound, so it must live in the
    same identity space the messages carry (on the Facebook-Login model that is
    the IG account behind the Page, NOT the Page id)."""

    model: str

    def self_id(self) -> str: ...

    def list_conversations(self, limit: int) -> list[Conversation]: ...

    def list_messages(
        self, conversation_id: str, limit: int
    ) -> list[DirectMessage]: ...

    def send(self, recipient_id: str, text: str) -> DirectMessage: ...


class FacebookLoginDmGateway:
    """``provider="meta"`` — Page-token model, behaviour unchanged.

    Resolves the Page id exactly as the router did inline before S3, so a
    Page-linked account that worked yesterday works identically today. Both
    lookups are memoised per instance; a gateway is built per request, and the
    previous shape paid for them on every route call."""

    model = "facebook_login"

    def __init__(self, adapter):
        self._adapter = adapter
        self._account = None
        self._page_id: str | None = None

    def _ig_account(self):
        if self._account is None:
            self._account = resolve_primary_ig_account(self._adapter)
        return self._account

    def _page(self) -> str:
        if self._page_id is None:
            self._page_id = resolve_primary_ig_page_id(self._adapter)
        return self._page_id

    def self_id(self) -> str:
        return self._ig_account().id

    def list_conversations(self, limit: int) -> list[Conversation]:
        return self._adapter.list_instagram_conversations(self._page(), limit)

    def list_messages(self, conversation_id: str, limit: int) -> list[DirectMessage]:
        return self._adapter.list_instagram_messages(
            conversation_id, self._page(), limit
        )

    def send(self, recipient_id: str, text: str) -> DirectMessage:
        return self._adapter.send_instagram_message(self._page(), recipient_id, text)


class InstagramLoginDmGateway:
    """``provider="instagram"`` — IG User token, no Page anywhere.

    ``/me`` IS the professional account, so ``self_id`` is one probe and the
    conversation/message calls take no page argument."""

    model = "instagram_login"

    def __init__(self, adapter):
        self._adapter = adapter
        self._me_id: str | None = None

    def self_id(self) -> str:
        if self._me_id is None:
            self._me_id = str(self._adapter.me().get("id") or "")
        return self._me_id

    def list_conversations(self, limit: int) -> list[Conversation]:
        return self._adapter.list_instagram_conversations(limit)

    def list_messages(self, conversation_id: str, limit: int) -> list[DirectMessage]:
        return self._adapter.list_instagram_messages(conversation_id, limit)

    def send(self, recipient_id: str, text: str) -> DirectMessage:
        return self._adapter.send_instagram_message(recipient_id, text)


_GATEWAY_BY_MODEL = {
    "facebook_login": FacebookLoginDmGateway,
    "instagram_login": InstagramLoginDmGateway,
}


def gateway_for(model: str, adapter) -> DmGateway:
    """Wrap ``adapter`` in the gateway registered for ``model``.

    Split out from :func:`build_dm_gateway` as a PURE function so the
    model→gateway mapping is testable directly — passing a model string and an
    adapter — instead of by patching the credential lookup out of the
    composition below. Tests that patch our own seams stop exercising them
    (`KB § PATTERNS/compliance/testing.md`); this keeps the mapping honest.

    An unregistered model raises rather than returning ``None``: unreachable
    through the service today (it returns one of the two models or raises), so
    this is a wiring assertion — a third model added there without a gateway
    here fails loudly instead of 500ing on a ``None`` call.
    """
    gateway_cls = _GATEWAY_BY_MODEL.get(model)
    if gateway_cls is None:
        raise ValueError(f"no DM gateway registered for model {model!r}")
    return gateway_cls(adapter)


def build_dm_gateway(account_id: UUID, org_id: UUID, *, svc=None) -> DmGateway:
    """Resolve ``account_id`` to the gateway for its stored messaging model.

    The model comes from the row's ``provider`` — the column S2's OAuth
    callback writes — so connecting an Instagram-Login account routes to the
    IG-Login path with no flag, no setting and no redeploy.

    Propagates ``IntegrationAccountNotFound`` / ``ValueError`` from the service
    unchanged; the router maps them to 404 exactly as it already does for the
    Facebook-Login path.

    Composition only — the two halves are tested independently: the provider→
    model half in ``TestGetDmAdapterForAccount`` (against a REAL
    ``IntegrationAccountService`` over SQLite), the model→gateway half in
    ``TestGatewayModelResolution`` via :func:`gateway_for`.
    """
    return gateway_for(*get_dm_adapter_for_account(account_id, org_id, svc=svc))
