"""Instagram Direct messages — account-scoped (Wave 3).

``GET /api/meta/instagram/conversations``, ``GET
/api/meta/instagram/messages``, ``POST /api/meta/instagram/messages``.
``ig_user_id`` resolves from the account (module docstring of
``meta_insights_router`` — the "exactly one linked IG account"
assumption); ``recipient_id``/``conversation_id`` are caller-supplied
(there are many threads per account).

DTO field names are shaped to match what ``useWhatsAppConnections``'
thread/message DTOs (``ChatSummary`` / ``MessageOut`` in
``app/schemas/whatsapp_connection.py``) expect, WHERE Graph's data
actually supports it — Wave 4's shared ``ChatWindow`` consumes both
providers through one adapter. Two honest divergences, documented
inline: (1) Graph's ``/conversations`` edge carries no message body or
unread count (unlike WAHA, which IS the chat) — those fields are
``None``, never a faked value; (2) the "who you're chatting with"
identity is ``contact_id`` (an IG-scoped user id, no username resolves
on this edge) rather than a JID."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

from app.routers._meta_common import (
    get_account_adapter,
    handle_meta_graph_error,
    resolve_primary_ig_account,
    resolve_primary_ig_page_id,
)
from app.services.meta import MetaAdapter, MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-dms"])


# ─── Response shapes ────────────────────────────────────────────────────
class MetaConversationOut(BaseModel):
    id: str
    contact_id: str | None = None
    contact: str | None = None
    last_message: str | None = None
    last_message_at: str | None = None
    unread: int | None = None


class MetaConversationsListOut(BaseModel):
    conversations: list[MetaConversationOut]


class MetaMessageOut(BaseModel):
    id: str
    conversation_id: str | None = None
    direction: str
    body: str | None = None
    created_at: str | None = None
    sender_id: str | None = None
    recipient_id: str | None = None


class MetaMessagesListOut(BaseModel):
    messages: list[MetaMessageOut]


class MetaSendMessageIn(StrictHttpModel):
    recipient_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


def _conversation_out(conv, *, self_id: str) -> MetaConversationOut:
    other = next((p for p in conv.participant_ids if p != self_id), None)
    return MetaConversationOut(
        id=conv.id,
        contact_id=other,
        # Graph's `/conversations` edge exposes no username for the
        # participant — `contact` falls back to the id itself so the FE
        # always has SOMETHING to render; a nicer label is a separate
        # lookup the FE may add later, never faked here.
        contact=other,
        # Not exposed by this Graph edge (no message body / unread count
        # on the conversations list) — left `None`, not a claimed "0
        # unread" / empty string. See module docstring.
        last_message=None,
        last_message_at=conv.updated_time.isoformat() if conv.updated_time else None,
        unread=None,
    )


def _message_out(msg, *, self_id: str, direction: str | None = None) -> MetaMessageOut:
    # READ path derives direction by comparing the message's sender to
    # "self" (the IG business account id). The SEND path passes
    # ``direction="outbound"`` explicitly — a just-sent message's
    # synthesized ``sender_id`` is the Page id (the send node on the
    # Facebook-Login model), which by construction won't equal the IG
    # account id, so the comparison would misread it as inbound.
    if direction is None:
        direction = "outbound" if msg.sender_id == self_id else "inbound"
    return MetaMessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        direction=direction,
        body=msg.text,
        created_at=msg.created_time.isoformat() if msg.created_time else None,
        sender_id=msg.sender_id,
        recipient_id=msg.recipient_id,
    )


# ─── GET /conversations ──────────────────────────────────────────────────
@router.get("/api/meta/instagram/conversations", response_model=MetaConversationsListOut)
def list_conversations(
    # Small default page: Graph rejects the IG conversations edge with (#1)
    # "Please reduce the amount of data you're asking for" on a busy inbox
    # when the page size + participant expansion get too heavy. 10 keeps the
    # first page cheap; callers can page for more.
    limit: int = Query(default=10, ge=1, le=50),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        account = resolve_primary_ig_account(adapter)
        page_id = resolve_primary_ig_page_id(adapter)
        conversations = adapter.list_instagram_conversations(page_id, limit)
    except MetaGraphError as exc:
        logger.warning("meta dms: conversations list failed: %s", exc)
        return handle_meta_graph_error(exc)

    return MetaConversationsListOut(
        conversations=[
            _conversation_out(c, self_id=account.id) for c in conversations
        ]
    )


# ─── GET /messages ───────────────────────────────────────────────────────
@router.get("/api/meta/instagram/messages", response_model=MetaMessagesListOut)
def list_messages(
    conversation_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        account = resolve_primary_ig_account(adapter)
        page_id = resolve_primary_ig_page_id(adapter)
        messages = adapter.list_instagram_messages(conversation_id, page_id, limit)
    except MetaGraphError as exc:
        logger.warning(
            "meta dms: messages list failed for %s: %s", conversation_id, exc
        )
        return handle_meta_graph_error(exc)

    return MetaMessagesListOut(
        messages=[_message_out(m, self_id=account.id) for m in messages]
    )


# ─── POST /messages ──────────────────────────────────────────────────────
@router.post("/api/meta/instagram/messages", response_model=MetaMessageOut)
def send_message(
    payload: MetaSendMessageIn,
    adapter: MetaAdapter = Depends(get_account_adapter),
):
    try:
        account = resolve_primary_ig_account(adapter)
        page_id = resolve_primary_ig_page_id(adapter)
        sent = adapter.send_instagram_message(
            page_id, payload.recipient_id, payload.text
        )
    except MetaGraphError as exc:
        logger.warning("meta dms: send failed to %s: %s", payload.recipient_id, exc)
        return handle_meta_graph_error(exc)

    return _message_out(sent, self_id=account.id, direction="outbound")


__all__ = ["router"]
