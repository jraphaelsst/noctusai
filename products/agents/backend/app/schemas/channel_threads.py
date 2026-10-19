"""Schemas of the shared-thread / controls API (Julia v2, contract §5 / §8.2).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"``): an
unknown field is a 422, never a silently dropped write.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel

__all__ = [
    "ControleOut",
    "ControleUpdateRequest",
    "DrenagemOut",
    "HandoffAceiteRequest",
    "HandoffDestinoOut",
    "HandoffOut",
    "LeadConsentOut",
    "OptInRequest",
    "OptOutOut",
    "OptOutRequest",
    "MensagemThreadOut",
    "ParticipanteEstadoRequest",
    "ParticipanteOut",
    "StudioParticipanteEstadoRequest",
    "ThreadMensagemOut",
    "ThreadMensagemRequest",
    "ThreadOut",
]


class ParticipanteOut(BaseModel):
    agent_key: str
    agent_nome: str
    estado: str
    entrou_em: datetime
    saiu_em: datetime | None
    motivo: str | None
    ultimo_turno_em: datetime | None
    #: A timed pause: past this instant the agent counts as active again.
    pausado_ate: datetime | None = None


class HandoffDestinoOut(BaseModel):
    tipo: Literal["agente", "humano", "papel"]
    agent_key: str | None = None
    user_id: UUID | None = None
    papel: str | None = None


class HandoffOut(BaseModel):
    """The hand-off note SW renders (and notifies the human operator with). ``identificacao_mascarada``
    holds MASKED fields only -- the raw documents never leave the encrypted identity store."""

    id: UUID
    thread_id: UUID
    lead_ref: str | None
    de_agent_key: str
    para: HandoffDestinoOut
    motivo_codigo: str
    resumo: str
    perfil: dict
    identificacao_completa: bool
    identificacao_mascarada: dict
    perguntas_abertas: list
    compromissos: list
    created_at: datetime
    aceito_em: datetime | None
    aceito_por: UUID | None


class HandoffAceiteRequest(StrictHttpModel):
    user_id: UUID


class OptInRequest(StrictHttpModel):
    origem: Literal["lead_iniciou", "formulario_meta", "campanha_ctwa", "importado"]
    em: datetime | None = None


class OptOutRequest(StrictHttpModel):
    em: datetime | None = None


class LeadConsentOut(BaseModel):
    lead_ref: str
    opt_in_em: datetime | None
    opt_in_origem: str | None
    opt_out_em: datetime | None
    #: The lead asked to stop and has not opted in again since: SW sends nothing.
    opt_out_ativo: bool


class OptOutOut(LeadConsentOut):
    #: How many agent participations the opt-out ended (every thread of the lead, every agent).
    participantes_encerrados: int


class ThreadOut(BaseModel):
    """``GET /api/channels/threads[/{id}]``. The lead's contact is NOT part of it (SW owns it)."""

    thread_id: UUID
    channel: str
    #: SW ``julia_contatos.id`` once the thread is linked to its lead (``None`` before).
    lead_ref: str | None
    participantes: list[ParticipanteOut]
    ultimo_turno_em: datetime | None
    ultima_mensagem_lead_em: datetime | None
    criado_em: datetime
    #: Messaging-policy consent of the lead (None until SW reports an opt-in).
    opt_in_em: datetime | None = None
    opt_in_origem: str | None = None
    opt_out_em: datetime | None = None
    #: SW must NOT send scheduled follow-ups: the lead opted out, or the token's agent is not an active
    #: participant (paused -- unless the timed pause ran out --, ended, concluded or transferred).
    reengajamento_suprimido: bool = False
    reengajamento_suprimido_motivo: str | None = None
    ultimo_handoff: HandoffOut | None = None


class ParticipanteEstadoRequest(StrictHttpModel):
    """``PATCH /api/channels/threads/{id}/participantes/{agent_key}`` (SW toggle). The actor is
    the SW user who clicked: it is recorded in the participant event and the audit log."""

    estado: Literal["pausado", "ativo"]
    motivo: str | None = Field(default=None, max_length=300)
    ator_user_id: UUID
    #: Pause until this instant (only with ``estado='pausado'``; must be in the future).
    ate: datetime | None = None


class StudioParticipanteEstadoRequest(StrictHttpModel):
    """Studio variant: the actor is the signed-in admin (from the JWT), never the body."""

    estado: Literal["pausado", "ativo"]
    motivo: str | None = Field(default=None, max_length=300)
    ate: datetime | None = None


class ThreadMensagemRequest(StrictHttpModel):
    """``POST /api/channels/threads/{id}/mensagens`` — append without a turn (a human attendant's
    message, or a lead message that must not be answered)."""

    role: Literal["user", "humano"]
    texto: str = Field(..., min_length=1, max_length=8000)
    provider_message_id: str = Field(..., min_length=1, max_length=256)
    at: datetime | None = None
    autor_user_id: UUID | None = None


class ThreadMensagemOut(BaseModel):
    message_id: UUID | None
    #: ``True`` when ``provider_message_id`` was already in the ledger (a retry): nothing appended.
    duplicado: bool


class DrenagemOut(BaseModel):
    """Drain progress: how many threads are still open and how old they are."""

    abertas: int
    #: Open threads idle for ``dreno_inatividade_dias`` or more: they count as closed (Q3).
    ociosas: int
    #: Open and still active (``abertas - ociosas``) — the drain is done when this reaches 0.
    efetivas: int
    concluida: bool
    idade_max_dias: int
    #: Days since the last lead message per open thread, oldest first (capped at 200).
    idades_dias: list[int]


class ControleOut(BaseModel):
    agent_key: str
    modo: Literal["ligado", "drenando", "desligado"]
    aceita_novos_leads: bool
    dreno_inatividade_dias: int
    threads_abertas: int
    drenagem: DrenagemOut


class ControleUpdateRequest(StrictHttpModel):
    """``PUT /api/studio/agents/{key}/controle``."""

    modo: Literal["ligado", "drenando", "desligado"]
    dreno_inatividade_dias: int | None = Field(default=None, ge=1, le=365)


class MensagemThreadOut(BaseModel):
    """One message of a thread as an org ADMIN may read it: the conversation only. System notices, tool
    calls / results, token usage and the version stamps (prompt-side internals) are never part of it."""

    id: UUID
    role: Literal["user", "assistant", "humano", "evento"]
    texto: str
    agent_key: str | None = None
    agent_nome: str | None = None
    autor_user_id: UUID | None = None
    created_at: datetime
