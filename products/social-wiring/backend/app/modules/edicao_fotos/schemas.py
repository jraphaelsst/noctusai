"""Inbound bodies — strict at the HTTP boundary (`extra="forbid"`), per
`KB § PATTERNS/backend/pydantic-strict-http.md`."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

EditTypeLiteral = Literal["cor_luz", "ceu", "declutter", "staging_virtual"]
SpeedLiteral = Literal["urgente", "economico"]


class ImovelRef(StrictHttpModel):
    org_id: UUID
    codigo: str = Field(min_length=1, max_length=40)


class LoteCreateBody(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=200)
    imovel: Optional[ImovelRef] = None


class VistaIngestBody(StrictHttpModel):
    codigo: str = Field(min_length=1, max_length=40)


class DecisaoBody(StrictHttpModel):
    decisao: Literal["aprovar", "rejeitar"]
    comentario: Optional[str] = Field(default=None, max_length=2000)


class OrgSettingsBody(StrictHttpModel):
    """FE `OrgConfiguracoes` (hooks.ts). `velocidade_padrao` equal to the
    platform default (or null) means "follow the platform"; `notificacoes_ativas`
    omitted keeps the stored value."""

    tipos_edicao_ativos: list[EditTypeLiteral] = Field(default_factory=list)
    modelo_editor_imagem: Optional[str] = Field(default=None, max_length=120)
    velocidade_padrao: Optional[SpeedLiteral] = None
    notificacoes_ativas: Optional[bool] = None


class PlatformSettingsBody(StrictHttpModel):
    velocidade_default: SpeedLiteral = "urgente"
    notificacoes_globais_ativas: bool = True
    preco_storage_gb_mes_usd: Optional[Decimal] = Field(default=None, ge=0)


class CuradorCreateBody(StrictHttpModel):
    user_id: UUID


__all__ = [
    "CuradorCreateBody",
    "DecisaoBody",
    "ImovelRef",
    "LoteCreateBody",
    "OrgSettingsBody",
    "PlatformSettingsBody",
    "VistaIngestBody",
]
