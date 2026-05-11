"""Pydantic models for LID-aware deferred authorization.

When the bot receives an inbound message from a WhatsApp ``@lid_*`` chat
(or unknown ``@c.us``) that doesn't map to an authorized user, the
webhook handler captures a ``pending_chat_identities`` row instead of
forwarding it to the GPT layer. An admin resolves the row later.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel

PendingChatStatus = Literal["pending", "resolved", "rejected"]


class PendingChatIdentityCreate(StrictHttpModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    push_name: str | None = Field(None, max_length=120)
    phone_hint: str | None = Field(None, max_length=32)
    status: PendingChatStatus = "pending"


class PendingChatIdentityResolve(StrictHttpModel):
    """Admin action: bind a pending chat to a real user (or reject it)."""

    status: PendingChatStatus
    resolved_to_user_id: UUID | None = None


class PendingChatIdentityOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    chat_id: str
    push_name: str | None
    phone_hint: str | None
    status: PendingChatStatus
    captured_at: datetime
    resolved_at: datetime | None
    resolved_to_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
