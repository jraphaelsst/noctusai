"""Intake/flow monitor — read-only window into live WhatsApp conversations.

Endpoints:
    GET  /api/whatsapp/intake/conversations              list + live state
    GET  /api/whatsapp/intake/conversations/{session_id}  state + messages
    POST /api/whatsapp/intake/conversations/{session_id}/cancel  clear stuck

Backing data:
- Conversation state: Redis ``whatsapp:conv:{session_id}`` (PendingUpload
  snapshot) + the ``whatsapp:active_uploads:{phone}`` counter — the same
  keys the intake state machine reads/writes. We read; we never mutate
  except the explicit cancel (which only DELETEs the pending key so a
  stuck flow can restart — transient state, the user can re-send).
- Message history: ``MessageStore.list_for_session`` over the
  seed-backed ``conversation_messages`` audit log (works on SQLite dev
  and Supabase prod alike via the store abstraction).

Auth: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern``.

Seed-first note: PendingUpload is social-wiring-specific (the
real-estate upload state machine), so this monitor is product-local.
The conversation-messages reader is seed-backed already; a generic
chatbot-conversation monitor is a future seed-lift candidate if a
second chatbot product needs the same surface (N=1 today —
accept-with-rationale, not pre-lifted).
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
)
from app.schemas.whatsapp import (
    IntakeCancelResult,
    IntakeConversationDetailDTO,
    IntakeConversationDTO,
    IntakeMessageDTO,
    PendingUpload,
)
from app.services.message_store import MessageStore
from app.services.whatsapp_intake_service import (
    _ACTIVE_UPLOADS_PREFIX,
    _REDIS_KEY_PREFIX,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp/intake", tags=["WhatsApp"])


def _redis_client():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _session_id_from_key(key: str) -> str:
    """Strip the ``whatsapp:conv:`` prefix back to the session id."""
    return key[len(_REDIS_KEY_PREFIX):] if key.startswith(_REDIS_KEY_PREFIX) else key


def _active_uploads(r, session_id: str) -> int:
    try:
        raw = r.get(f"{_ACTIVE_UPLOADS_PREFIX}{session_id}")
        return int(raw) if raw else 0
    except (ValueError, TypeError):
        return 0


def _to_dto(session_id: str, pending: PendingUpload, active: int) -> IntakeConversationDTO:
    return IntakeConversationDTO(
        session_id=session_id,
        state=pending.state,
        product_code=pending.product_code or None,
        drive_url=pending.drive_url,
        video_filename=pending.video_filename or pending.local_video_filename,
        video_format=pending.video_format,
        candidate_count=len(pending.candidate_videos),
        active_uploads=active,
    )


@router.get("/conversations", response_model=list[IntakeConversationDTO])
def list_conversations(
    auth: tuple = Depends(get_current_user_org),
) -> list[IntakeConversationDTO]:
    """Every conversation with a live pending-state snapshot in Redis.

    Ordered by non-idle first (states needing attention surface up top),
    then session id for stable rendering.
    """
    _user, _token, _raw_org = auth
    r = _redis_client()
    out: list[IntakeConversationDTO] = []
    for key in r.scan_iter(match=f"{_REDIS_KEY_PREFIX}*", count=100):
        raw = r.get(key)
        if not raw:
            continue
        try:
            pending = PendingUpload(**json.loads(raw))
        except Exception:
            logger.warning("intake monitor: unparseable state at %s — skipping", key)
            continue
        sid = _session_id_from_key(key)
        out.append(_to_dto(sid, pending, _active_uploads(r, sid)))
    out.sort(key=lambda c: (c.state == "idle", c.session_id))
    return out


@router.get(
    "/conversations/{session_id}",
    response_model=IntakeConversationDetailDTO,
)
def get_conversation(
    session_id: str,
    message_limit: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> IntakeConversationDetailDTO:
    """One conversation's live state + recent message history."""
    _user, _token, raw_org = auth
    org_id: UUID = coerce_org_uuid(raw_org)
    r = _redis_client()

    raw = r.get(f"{_REDIS_KEY_PREFIX}{session_id}")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No live conversation state for session {session_id!r}",
        )
    try:
        pending = PendingUpload(**json.loads(raw))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Conversation state for {session_id!r} is corrupt: {exc}",
        )

    conversation = _to_dto(session_id, pending, _active_uploads(r, session_id))

    messages: list[IntakeMessageDTO] = []
    try:
        store = MessageStore(admin_supabase=get_admin_client(), org_id=org_id)
        rows = store.list_for_session(session_id=session_id, limit=message_limit)
        messages = [
            IntakeMessageDTO(
                direction=row.get("direction", ""),
                body=row.get("body", ""),
                created_at=str(row["created_at"]) if row.get("created_at") else None,
                provider_message_id=row.get("provider_message_id"),
            )
            for row in rows
        ]
    except Exception:
        # The audit log is best-effort context, not the source of truth
        # for state — a store hiccup must not 500 the state view.
        logger.exception(
            "intake monitor: message history fetch failed for %s", session_id
        )

    return IntakeConversationDetailDTO(
        conversation=conversation, messages=messages
    )


@router.post(
    "/conversations/{session_id}/cancel",
    response_model=IntakeCancelResult,
)
def cancel_conversation(
    session_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> IntakeCancelResult:
    """Clear a stuck conversation's pending state.

    Only DELETEs ``whatsapp:conv:{session_id}`` — transient debounce/
    state-machine data. The user can immediately re-send a command; no
    durable record (conversation_messages audit log) is touched.
    """
    _user, _token, _raw_org = auth
    r = _redis_client()
    deleted = r.delete(f"{_REDIS_KEY_PREFIX}{session_id}")
    return IntakeCancelResult(session_id=session_id, cleared=bool(deleted))
