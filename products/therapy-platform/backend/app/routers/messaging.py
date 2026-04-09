"""
Messaging Router — conversations, messages, blocks, reports, read receipts.

Prefix: /api/conversations
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
    get_clinic_id_for_user,
)
from app.responses import paginated_response, success_response, ok_response
from app.schemas.messaging import (
    SendMessageRequest,
    StartConversationRequest,
    MessageReportRequest,
    BlockUserRequest,
)
from app.services import messaging_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["Messaging"])


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@router.post("")
async def start_conversation(
    body: StartConversationRequest,
    authorization: Optional[str] = Header(None),
):
    """Start a new conversation or resume an existing one.

    Finds an existing conversation between the two participants. If none
    exists, creates one and sends the initial message.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    sender_type = "user"
    clinic_id_for_clinic = None
    if role == "clinic_admin":
        clinic_id_for_clinic = get_clinic_id_for_user(user)

    conv = await messaging_service.find_or_create_conversation(
        sender_id=user.id,
        sender_type=sender_type,
        participant_type=body.participant_type,
        participant_id=body.participant_id,
        clinic_id=body.clinic_id,
        db=db,
    )

    # Send the initial message
    sender_clinic_id = get_clinic_id_for_user(user) if role == "clinic_admin" else None
    msg = await messaging_service.send_message(
        conversation_id=conv["id"],
        sender_user_id=user.id,
        sender_type=sender_type,
        content=body.initial_message,
        message_type="text",
        sender_clinic_id=sender_clinic_id,
        db=db,
    )

    return success_response({
        "conversation": conv,
        "message": msg,
    })


@router.get("")
async def list_conversations(
    authorization: Optional[str] = Header(None),
    filter_type: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List conversations for the current user (role-scoped)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    clinic_id = get_clinic_id_for_user(user)
    db = get_user_client(token)

    filters = {}
    if filter_type:
        filters["filter_type"] = filter_type
    if busca:
        filters["busca"] = busca

    data, total = await messaging_service.list_conversations(
        user_id=user.id,
        user_role=role,
        clinic_id=clinic_id,
        filters=filters,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/unread-count")
async def get_unread_count(
    authorization: Optional[str] = Header(None),
):
    """Get total unread message count across all conversations."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    clinic_id = get_clinic_id_for_user(user)
    db = get_user_client(token)

    count = await messaging_service.get_unread_count(
        user_id=user.id,
        user_role=role,
        clinic_id=clinic_id,
        db=db,
    )
    return success_response({"unread_count": count})


# ---------------------------------------------------------------------------
# Messages within a conversation
# ---------------------------------------------------------------------------

@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get messages for a conversation (validates access)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    clinic_id = get_clinic_id_for_user(user)
    db = get_user_client(token)

    data, total = await messaging_service.get_messages(
        conversation_id=conversation_id,
        user_id=user.id,
        user_role=role,
        clinic_id=clinic_id,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    authorization: Optional[str] = Header(None),
):
    """Send a message in a conversation."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    sender_type = "user"
    sender_clinic_id = None
    if role == "clinic_admin":
        sender_clinic_id = get_clinic_id_for_user(user)

    msg = await messaging_service.send_message(
        conversation_id=conversation_id,
        sender_user_id=user.id,
        sender_type=sender_type,
        content=body.content,
        message_type=body.message_type,
        sender_clinic_id=sender_clinic_id,
        db=db,
    )
    return success_response(msg)


# ---------------------------------------------------------------------------
# Conversation management
# ---------------------------------------------------------------------------

@router.patch("/{conversation_id}/read")
async def mark_as_read(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
):
    """Mark all messages in a conversation as read."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.mark_as_read(
        conversation_id=conversation_id,
        user_id=user.id,
        db=db,
    )
    return ok_response(result.get("message", "Conversa marcada como lida"))


@router.post("/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
):
    """Archive a conversation (per-user soft delete)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.archive_conversation(
        conversation_id=conversation_id,
        user_id=user.id,
        db=db,
    )
    return ok_response(result.get("message", "Conversa arquivada"))


@router.post("/{conversation_id}/mute")
async def mute_conversation(
    conversation_id: str,
    mute: bool = Query(True),
    authorization: Optional[str] = Header(None),
):
    """Mute or unmute a conversation."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.mute_conversation(
        conversation_id=conversation_id,
        user_id=user.id,
        mute=mute,
        db=db,
    )
    return ok_response(result.get("message", "Preferência atualizada"))


# ---------------------------------------------------------------------------
# Message deletion and reporting
# ---------------------------------------------------------------------------

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    authorization: Optional[str] = Header(None),
):
    """Hard-delete a message (sender only)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.delete_message(
        message_id=message_id,
        user_id=user.id,
        db=db,
    )
    return ok_response(result.get("message", "Mensagem excluída"))


@router.post("/messages/{message_id}/report")
async def report_message(
    message_id: str,
    body: MessageReportRequest,
    authorization: Optional[str] = Header(None),
):
    """Report a message for moderation."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get the conversation_id from the message
    check = (
        db.table("messages")
        .select("conversation_id")
        .eq("id", message_id)
        .execute()
    )
    from app.dependencies import first_or_none
    msg = first_or_none(check)
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    result = await messaging_service.report_message(
        conversation_id=msg["conversation_id"],
        message_id=message_id,
        reporter_id=user.id,
        reason=body.reason,
        db=db,
    )
    return success_response(result)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

@router.post("/block")
async def block_user(
    body: BlockUserRequest,
    authorization: Optional[str] = Header(None),
):
    """Block a user."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.block_user(
        blocker_id=user.id,
        blocked_id=body.blocked_user_id,
        db=db,
    )
    return ok_response(result.get("message", "Usuário bloqueado"))


@router.delete("/block/{user_id}")
async def unblock_user(
    user_id: str,
    authorization: Optional[str] = Header(None),
):
    """Unblock a user."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = await messaging_service.unblock_user(
        blocker_id=user.id,
        blocked_id=user_id,
        db=db,
    )
    return ok_response(result.get("message", "Usuário desbloqueado"))
