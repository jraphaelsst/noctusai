"""Schemas for the `assinaturas` domain — contract §Manager+member views,
amendment P3 (moderador redaction).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ASSINATURA_ESTADOS = ("iniciada", "ativa", "inadimplente", "pausada", "cancelada")


class AssinaturaCancelRequest(BaseModel):
    """Request body for `POST /api/assinaturas/{id}/cancelar`."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(..., min_length=1, max_length=500)


class Assinatura(BaseModel):
    """Full response shape — `admin` role. Contract §Manager+member views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membro_id: UUID
    membro_nome: Optional[str] = None
    plano_id: UUID
    plano_nome: Optional[str] = None
    gateway: str
    estado: str
    metodo: str
    ciclo: str
    assinatura_externa_id: Optional[str] = None
    iniciada_em: Optional[datetime] = None
    ativa_em: Optional[datetime] = None
    cancelada_em: Optional[datetime] = None


class AssinaturaModerador(BaseModel):
    """Redacted response shape — `moderador` role (amendment P3).

    An EXHAUSTIVE allow-list, not a partial mask: every field not listed
    here (`id`, `membro_id`, `plano_id`, `gateway`,
    `assinatura_externa_id`, `iniciada_em`, `cancelada_em`) is ABSENT
    from the serialized dict, not merely nulled — the contract's own
    test wording ("assert the omitted keys are absent, not just falsy").
    """

    model_config = ConfigDict(from_attributes=True)

    estado: str
    metodo: str
    ciclo: str
    plano_nome: Optional[str] = None
    membro_nome: Optional[str] = None
    ativa_em: Optional[datetime] = None
