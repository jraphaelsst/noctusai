"""Schemas for module 3 — WhatsApp (grupos, sincronização, transmissões,
ingest, flags). Contract: community-m3-contract.md.

`moderador` redaction (D3: "moderador sees masked phones and never an
invite link") follows module 2's P3 precedent — an EXHAUSTIVE allow-list
schema per redacted shape, not a partial mask on the full schema, so a
forgotten field can never leak through a shared base class.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

GRUPO_ESTADOS = ("proposto", "confirmado", "aplicado", "aplicado_parcial", "cancelado", "expirado")


def mask_telefone(telefone: str | None) -> str | None:
    """Mask a phone to its last 4 digits (contract §4: "telefone masked
    to last 4"). ``None`` stays ``None`` (no phone on file — never
    fabricate one)."""
    if not telefone:
        return None
    digits = telefone[-4:]
    return f"***{digits}"


# ── Grupos ───────────────────────────────────────────────────────────


class GrupoCreate(BaseModel):
    """Request body for `POST /api/whatsapp/grupos`.

    Register an EXISTING group by `chat_id`, or `{"criar": true, "nome": "..."}`
    to call `create_group`.
    """

    model_config = ConfigDict(extra="forbid")

    chat_id: Optional[str] = None
    criar: bool = False
    nome: Optional[str] = Field(None, min_length=1, max_length=120)
    descricao: Optional[str] = Field(None, max_length=500)
    somente_admin: bool = False


class GrupoUpdate(BaseModel):
    """Request body for `PATCH /api/whatsapp/grupos/{id}` — partial update."""

    model_config = ConfigDict(extra="forbid")

    nome: Optional[str] = Field(None, min_length=1, max_length=120)
    descricao: Optional[str] = Field(None, max_length=500)
    ativo: Optional[bool] = None
    somente_admin: Optional[bool] = None


class GrupoRosterItem(BaseModel):
    """Roster row — full shape (`admin`)."""

    model_config = ConfigDict(from_attributes=True)

    participante_jid: str
    membro_id: Optional[UUID] = None
    membro_nome: Optional[str] = None
    telefone: Optional[str] = None
    papel: str
    visto_em: datetime


class GrupoRosterItemModerador(BaseModel):
    """Roster row — redacted shape (`moderador`, D3). `participante_jid`
    (which embeds the raw phone digits for a `@c.us` JID) is OMITTED,
    not just the phone field — otherwise the mask is defeated."""

    model_config = ConfigDict(from_attributes=True)

    membro_id: Optional[UUID] = None
    membro_nome: Optional[str] = None
    telefone_mascarado: Optional[str] = None
    papel: str
    visto_em: datetime


class Grupo(BaseModel):
    """Full response shape (`admin` + `moderador` — no per-field
    redaction on the group itself; only the roster + convite are
    role-gated)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    chat_id: str
    descricao: Optional[str] = None
    ativo: bool
    somente_admin: bool
    participantes_observados: int
    sincronizado_em: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrupoListResponse(BaseModel):
    items: list[Grupo]
    total: int


class SincronizarRosterResponse(BaseModel):
    participantes: int


class ConviteOut(BaseModel):
    """`GET /api/whatsapp/grupos/{id}/convite` — admin only. Never logged."""

    link: str


class SessaoOut(BaseModel):
    """`GET /api/whatsapp/sessao`."""

    estado: str
    sessao: str


# ── Sincronização (lotes) ───────────────────────────────────────────────


class LoteCreate(BaseModel):
    """Request body for `POST /api/whatsapp/grupos/{id}/lotes`."""

    model_config = ConfigDict(extra="forbid")

    acao: str = Field(..., pattern="^(adicionar|remover)$")


class LoteConfirmarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmo: bool = Field(...)


class LoteItem(BaseModel):
    """Lote item — full shape (`admin`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membro_id: Optional[UUID] = None
    membro_nome: Optional[str] = None
    participante_jid: str
    telefone: Optional[str] = None
    resultado: str
    codigo_waha: Optional[int] = None
    processado_em: Optional[datetime] = None


class LoteItemModerador(BaseModel):
    """Lote item — redacted shape (`moderador`, D3)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membro_id: Optional[UUID] = None
    membro_nome: Optional[str] = None
    telefone_mascarado: Optional[str] = None
    resultado: str
    processado_em: Optional[datetime] = None


class Lote(BaseModel):
    """Full lote response (`admin`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grupo_id: UUID
    acao: str
    estado: str
    total_itens: int
    proposto_por: Optional[UUID] = None
    confirmado_por: Optional[UUID] = None
    proposto_em: datetime
    confirmado_em: Optional[datetime] = None
    aplicado_em: Optional[datetime] = None
    expira_em: datetime
    motivo_falha: Optional[str] = None
    ignorados: list[dict] = Field(default_factory=list)
    itens: list[LoteItem] = Field(default_factory=list)


class LoteModerador(BaseModel):
    """Redacted lote response (`moderador`, D3)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grupo_id: UUID
    acao: str
    estado: str
    total_itens: int
    proposto_em: datetime
    confirmado_em: Optional[datetime] = None
    aplicado_em: Optional[datetime] = None
    expira_em: datetime
    motivo_falha: Optional[str] = None
    itens: list[LoteItemModerador] = Field(default_factory=list)


class LoteListResponse(BaseModel):
    items: list
    total: int


class ConvitePendenteItem(BaseModel):
    membro_id: Optional[UUID] = None
    membro_nome: Optional[str] = None
    telefone: Optional[str] = None
    participante_jid: str


class ConvitesPendentesResponse(BaseModel):
    items: list[ConvitePendenteItem]
    total: int
    link: Optional[str] = None


# ── Transmissões ─────────────────────────────────────────────────────────


class TransmissaoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(..., min_length=1, max_length=200)
    corpo: str = Field(..., min_length=1)
    tipo: str = Field(..., pattern="^(anuncio|lembrete_evento|conteudo)$")
    grupo_ids: list[str] = Field(..., min_length=1)
    agendada_para: Optional[datetime] = None


class TransmissaoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    corpo: Optional[str] = Field(None, min_length=1)
    tipo: Optional[str] = Field(None, pattern="^(anuncio|lembrete_evento|conteudo)$")
    grupo_ids: Optional[list[str]] = None
    agendada_para: Optional[datetime] = None


class TransmissaoDestino(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grupo_id: UUID
    estado: str
    provider_message_id: Optional[str] = None
    erro: Optional[str] = None
    enviado_em: Optional[datetime] = None


class Transmissao(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    titulo: str
    corpo: str
    tipo: str
    estado: str
    agendada_para: Optional[datetime] = None
    enviada_em: Optional[datetime] = None
    criada_por: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    destinos: list[TransmissaoDestino] = Field(default_factory=list)


class TransmissaoListResponse(BaseModel):
    items: list[Transmissao]
    total: int


class TransmissaoEnviarResponse(BaseModel):
    transmissao_id: UUID
    destinos: int


# ── Flags ────────────────────────────────────────────────────────────────


class FlagResolverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: str = Field(..., pattern="^(resolvida|descartada)$")
    nota: Optional[str] = Field(None, max_length=1000)


class Flag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mensagem_id: UUID
    grupo_id: Optional[UUID] = None
    categoria: Optional[str] = None
    severidade: str
    justificativa: Optional[str] = None
    modelo: Optional[str] = None
    prompt_versao: Optional[str] = None
    estado: str
    resolvido_por: Optional[UUID] = None
    resolvido_em: Optional[datetime] = None
    created_at: datetime


class FlagListResponse(BaseModel):
    items: list[Flag]
    total: int
