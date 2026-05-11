"""Pydantic models for conversation history + summaries."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel

MessageDirection = Literal["inbound", "outbound", "system"]


class ConversationMessageCreate(StrictHttpModel):
    """A persisted WhatsApp message (inbound from user, outbound from bot, or system note)."""

    provider_message_id: str | None = Field(None, max_length=255)
    user_id: UUID | None = None
    chat_id: str | None = Field(None, max_length=255)
    direction: MessageDirection
    message_text: str = Field(..., min_length=1)
    structured_payload: dict[str, Any] | None = None


class ConversationMessageOut(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    provider_message_id: str | None
    user_id: UUID | None
    chat_id: str | None
    direction: MessageDirection
    message_text: str
    structured_payload: dict[str, Any] | None
    created_at: datetime


class ConversationSummaryCreate(StrictHttpModel):
    # ``model_used`` collides with pydantic's protected ``model_`` namespace
    # but is a domain-justified field name (which OpenAI model labeled the
    # summary). Disable the namespace guard for these summary schemas only.
    model_config = ConfigDict(protected_namespaces=())

    user_id: UUID | None = None
    conversation_id: str = Field(..., max_length=64)
    summary_text: str
    label: dict[str, Any] | None = None
    message_count: int = Field(0, ge=0)
    model_used: str | None = Field(None, max_length=80)
    started_at: datetime | None = None
    ended_at: datetime


class ConversationSummaryOut(StrictHttpModel):
    # See note on ConversationSummaryCreate — protected_namespaces=() lets
    # ``model_used`` round-trip without a pydantic warning.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    org_id: UUID
    user_id: UUID | None
    conversation_id: str
    summary_text: str
    label: dict[str, Any] | None
    message_count: int
    model_used: str | None
    started_at: datetime | None
    ended_at: datetime
    created_at: datetime
