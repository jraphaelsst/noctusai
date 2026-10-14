"""Schemas of the channel turn API (Lais contract §3.1 / §3.2 / §4).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"``
→ 422 on an unknown field). The caps are the §10.1 M4 flood limits: a batch is
1..20 messages, each 1..8000 characters, 16 000 characters in total — enforced
here, BEFORE any model call or write.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

__all__ = [
    "BATCH_MAX_CHARS",
    "BATCH_MAX_MESSAGES",
    "MESSAGE_MAX_CHARS",
    "ChannelActionOut",
    "ChannelAgentStatusOut",
    "ChannelContact",
    "ChannelDeleteRequest",
    "ChannelInboundMessage",
    "ChannelRef",
    "ChannelReplyOut",
    "ChannelTokenCreateRequest",
    "ChannelTokenOut",
    "ChannelTurnRequest",
    "ChannelTurnResponse",
    "ChannelUsageOut",
]

BATCH_MAX_MESSAGES = 20
MESSAGE_MAX_CHARS = 8000
BATCH_MAX_CHARS = 16_000

#: Channels the turn API accepts (page 0: WhatsApp via WAHA / Cloud API).
Channel = Literal["whatsapp"]


class ChannelRef(StrictHttpModel):
    """The conversation identity within a channel: the connection (the number)
    and the chat on it. Unique per org + agent."""

    connection_id: UUID
    chat_id: str = Field(..., min_length=1, max_length=256)

    def canonical(self) -> dict[str, str]:
        return {"connection_id": str(self.connection_id), "chat_id": self.chat_id}


class ChannelContact(StrictHttpModel):
    """Display metadata only. NEVER put into a prompt (§10.1 M3)."""

    phone_e164: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=200)


class ChannelInboundMessage(StrictHttpModel):
    texto: str = Field(..., min_length=1, max_length=MESSAGE_MAX_CHARS)
    provider_message_id: str = Field(..., min_length=1, max_length=256)
    at: datetime

    @field_validator("texto")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("texto must not be blank")
        return v


class ChannelTurnRequest(StrictHttpModel):
    agent_key: str = Field(..., min_length=1, max_length=64)
    channel: Channel
    channel_ref: ChannelRef
    contact: ChannelContact = Field(default_factory=ChannelContact)
    messages: list[ChannelInboundMessage] = Field(..., min_length=1, max_length=BATCH_MAX_MESSAGES)

    @model_validator(mode="after")
    def _batch_caps(self) -> "ChannelTurnRequest":
        total = sum(len(m.texto) for m in self.messages)
        if total > BATCH_MAX_CHARS:
            raise ValueError(f"the batch holds {total} characters; the maximum is {BATCH_MAX_CHARS}")
        ids = [m.provider_message_id for m in self.messages]
        if len(set(ids)) != len(ids):
            raise ValueError("provider_message_id must be unique within a batch")
        return self


class ChannelReplyOut(BaseModel):
    partes: list[str]


class ChannelActionOut(BaseModel):
    type: Literal["handoff"]
    motivo: str


class ChannelUsageOut(BaseModel):
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ChannelTurnResponse(BaseModel):
    conversation_id: UUID
    reply: ChannelReplyOut
    actions: list[ChannelActionOut]
    status: Literal["respondido", "silencio", "handoff"]
    usage: ChannelUsageOut


class ChannelAgentStatusOut(BaseModel):
    agent_key: str
    nome: str
    ativo: bool
    versao_ativa: int | None
    provider: str | None
    model: str | None
    llm_configurado: bool


class ChannelDeleteRequest(StrictHttpModel):
    """``DELETE /api/channels/conversations`` — deletion on request (LGPD)."""

    agent_key: str = Field(..., min_length=1, max_length=64)
    channel: Channel
    channel_ref: ChannelRef


class ChannelTokenCreateRequest(StrictHttpModel):
    product: Literal["social-wiring"]
    label: str = Field(..., min_length=1, max_length=120)


class ChannelTokenOut(BaseModel):
    """Returned ONCE at mint. ``token`` is never retrievable again."""

    id: UUID
    token: str
    prefix: str
    expires_at: datetime
    scopes: list[str]
