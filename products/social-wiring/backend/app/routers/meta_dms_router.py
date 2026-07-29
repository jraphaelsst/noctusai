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

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

from app.routers._dm_gateway import DmGateway
from app.routers._meta_common import get_dm_gateway, handle_meta_graph_error
from app.services.meta import MetaGraphError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-dms"])

# Meta's "query expired" signal for the IG conversations edge. On an account
# that holds `instagram_manage_messages` only at STANDARD access, Graph will
# only return DM threads with users who have a role on the app. A real
# business inbox (thousands of ordinary followers) makes Graph scan
# conversations it is allowed to return NONE of, and the query expires:
# error code -2 / subcode 2534084 ("solicite acesso avançado à permissão
# instagram_manage_messages"). In practice the httpx read timeout (30s) fires
# BEFORE Meta's own -2 lands, so the transport wrapper surfaces it as
# http_status 504. Either way it is a structural, cacheable ADVANCED-ACCESS
# gate — the remedy is Meta App Review, not a retry — so the DMs tab must
# render the honest App-Review notice, never a 30s skeleton → scary 502.
_ADVANCED_ACCESS_SUBCODE = 2534084


def _is_dm_advanced_access_gate(exc: MetaGraphError) -> bool:
    """True when a conversations-list failure is the Standard-Access
    "too many non-role conversations → query expired" symptom (Meta's
    -2/2534084) OR the httpx read-timeout that precedes it (504). Kept
    LOCAL to the DMs conversations read: a timeout on any OTHER Meta edge
    still maps through `handle_meta_graph_error` (→ 502), so this never
    mislabels unrelated Graph slowness fleet-wide."""
    return (
        exc.error_subcode == _ADVANCED_ACCESS_SUBCODE
        or exc.code == -2
        or exc.http_status == 504
    )


_DM_ADVANCED_ACCESS_MESSAGE = (
    "As mensagens diretas do Instagram exigem Acesso Avançado à permissão "
    "instagram_manage_messages (Revisão do app da Meta). Em Acesso Padrão, a "
    "consulta expira em contas com muitas conversas de seguidores. Envie o "
    "caso de uso de mensagens do Instagram para análise no Painel de Apps da "
    "Meta para ativar as DMs."
)


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
    gateway: DmGateway = Depends(get_dm_gateway),
):
    try:
        self_id = gateway.self_id()
        conversations = gateway.list_conversations(limit)
    except MetaGraphError as exc:
        logger.warning("meta dms: conversations list failed: %s", exc)
        if _is_dm_advanced_access_gate(exc):
            # Fail fast into an honest, actionable App-Review state (a 200,
            # cached by the FE) instead of a raw 502 the tab can't explain.
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "requires_app_review": True,
                    "error": _DM_ADVANCED_ACCESS_MESSAGE,
                },
            )
        return handle_meta_graph_error(exc)

    return MetaConversationsListOut(
        conversations=[_conversation_out(c, self_id=self_id) for c in conversations]
    )


# ─── GET /messages ───────────────────────────────────────────────────────
@router.get("/api/meta/instagram/messages", response_model=MetaMessagesListOut)
def list_messages(
    conversation_id: str = Query(...),
    limit: int = Query(default=25, ge=1, le=100),
    gateway: DmGateway = Depends(get_dm_gateway),
):
    try:
        self_id = gateway.self_id()
        messages = gateway.list_messages(conversation_id, limit)
    except MetaGraphError as exc:
        logger.warning(
            "meta dms: messages list failed for %s: %s", conversation_id, exc
        )
        return handle_meta_graph_error(exc)

    return MetaMessagesListOut(
        messages=[_message_out(m, self_id=self_id) for m in messages]
    )


# ─── POST /messages ──────────────────────────────────────────────────────
@router.post("/api/meta/instagram/messages", response_model=MetaMessageOut)
def send_message(
    payload: MetaSendMessageIn,
    gateway: DmGateway = Depends(get_dm_gateway),
):
    try:
        self_id = gateway.self_id()
        sent = gateway.send(payload.recipient_id, payload.text)
    except MetaGraphError as exc:
        logger.warning("meta dms: send failed to %s: %s", payload.recipient_id, exc)
        return handle_meta_graph_error(exc)

    return _message_out(sent, self_id=self_id, direction="outbound")


__all__ = ["router"]
