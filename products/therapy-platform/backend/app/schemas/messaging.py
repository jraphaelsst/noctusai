"""
Messaging schemas — conversations, messages, reports, blocks.
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """Send a message in a conversation."""

    content: str = Field(..., min_length=1, max_length=5000)
    message_type: Literal["text", "image", "audio"] = "text"


class StartConversationRequest(BaseModel):
    """Start a new conversation or resume an existing one."""

    participant_type: Literal["user", "clinic", "platform_support"]
    participant_id: Optional[str] = None
    clinic_id: Optional[str] = None
    initial_message: str = Field(..., min_length=1, max_length=5000)


class MessageReportRequest(BaseModel):
    """Report a message for moderation."""

    reason: str = Field(..., min_length=10, max_length=2000)


class ReportReviewRequest(BaseModel):
    """Admin reviews a message report."""

    resolution: str = Field(..., min_length=1, max_length=2000)


class BlockUserRequest(BaseModel):
    """Block another user."""

    blocked_user_id: str


class ConversationFilters(BaseModel):
    """Filters for listing conversations."""

    filter_type: Optional[Literal[
        "all", "unread", "patients", "therapists", "clinics", "support"
    ]] = None
    busca: Optional[str] = None
