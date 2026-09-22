"""Pydantic schemas for the Agentes API (contract §E.2,
``projects/julia-agents-academia-CONTRACT.md``).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra=
"forbid"`` -> 422 on an unknown field — contract §0 "Strictness"). Response
models are plain ``BaseModel`` (contract §0: "Response models may gain
fields; consumers must ignore unknown response fields.").
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from noctusai_lib.api import StrictHttpModel

# ── Agents (§E.2 "GET /api/agents", "POST /api/agents/{key}/toggle") ───────


class EstadoExternoOut(BaseModel):
    auto_reply_enabled: bool


class AgentOut(BaseModel):
    key: str
    nome: str
    runtime: str
    owner_product: str | None
    ativo: bool
    estado_externo: EstadoExternoOut | None = None
    #: Set only when `estado_externo` is `None` because the bridge call to
    #: social-wiring failed (contract: "null plus aviso if unreachable").
    aviso: str | None = None


class AgentListOut(BaseModel):
    items: list[AgentOut]
    total: int


class AgentToggleRequest(StrictHttpModel):
    ativo: bool


# ── Persona (§E.2 "GET/PUT /api/agents/julia/persona") ─────────────────────


class PersonaOut(BaseModel):
    versao: int
    nome: str
    papel: str
    tom: str | None
    system_prompt_append: str | None
    model: str
    effort: str
    idioma: str
    org_display_name: str | None
    project_display_name: str | None
    ativa: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PersonaUpdateRequest(StrictHttpModel):
    nome: str = Field(..., min_length=1)
    papel: str = Field(..., min_length=1)
    model: str
    effort: str
    tom: str | None = None
    system_prompt_append: str | None = None
    idioma: str = "pt-BR"
    org_display_name: str | None = None
    project_display_name: str | None = None


# ── Conversations (§E.2) ────────────────────────────────────────────────────


class ConversationOut(BaseModel):
    id: UUID
    agent_id: UUID
    owner_user_id: UUID
    titulo: str | None
    sdk_session_id: str | None
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Agent Studio §D6 (additive).
    agent_key: str
    version_id: UUID | None = None
    client_id: UUID | None = None


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int


class ConversationCreateRequest(StrictHttpModel):
    titulo: str | None = None
    # Agent Studio §D6: which agent; omitted ⇒ Julia (her page sends nothing).
    agent_key: str = Field(default="julia", min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    #: Studio agents only; must belong to that agent AND be active.
    client_id: UUID | None = None


class ConversationUpdateRequest(StrictHttpModel):
    """``PATCH /api/conversations/{conversation_id}`` — rename only."""

    titulo: str

    @field_validator("titulo")
    @classmethod
    def _titulo_trimmed_and_bounded(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("titulo não pode ficar em branco")
        if len(v) > 120:
            raise ValueError("titulo deve ter no máximo 120 caracteres")
        return v


# ── Messages (§E.2) ──────────────────────────────────────────────────────


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    texto: str
    blocks: list[dict[str, Any]]
    token_usage: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    # Agent Studio §D6/§A7 (additive): set on a studio agent's assistant messages.
    version_id: UUID | None = None
    compiled_hash: str | None = None
    # Contract §L "Controle de custo" (additive): an assistant message's turn
    # cost/token counts (SDK ResultMessage) — null for user/system rows and
    # for any turn that reported no ResultMessage.
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class MessageListOut(BaseModel):
    items: list[MessageOut]
    total: int


class MessageCreateRequest(StrictHttpModel):
    texto: str = Field(..., min_length=1, max_length=8000)


class MessagePostResponse(BaseModel):
    mensagem: MessageOut
    status: Literal["processando"] = "processando"


# ── Approvals (§E.2) ─────────────────────────────────────────────────────


class ApprovalOut(BaseModel):
    id: UUID
    conversation_id: UUID
    tool_name: str
    tool_input: dict[str, Any]
    classe: str
    resumo: str
    diff: dict[str, Any] | None
    decision: str
    decided_by: UUID | None
    decided_at: datetime | None
    requested_by: UUID
    created_at: datetime
    updated_at: datetime


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]
    total: int


class ApprovalDecisionRequest(StrictHttpModel):
    aprovada: bool


__all__ = [
    "AgentListOut",
    "AgentOut",
    "AgentToggleRequest",
    "ApprovalDecisionRequest",
    "ApprovalListOut",
    "ApprovalOut",
    "ConversationCreateRequest",
    "ConversationListOut",
    "ConversationOut",
    "EstadoExternoOut",
    "MessageCreateRequest",
    "MessageListOut",
    "MessageOut",
    "MessagePostResponse",
    "PersonaOut",
    "PersonaUpdateRequest",
]
