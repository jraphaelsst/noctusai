"""Contracts for Módulo 1 — CRM, orçamentos e onboarding."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "LeadPublicoIn", "LeadOut", "ItemEscopoIn", "EstimativaOut",
    "OrcamentoCreate", "OrcamentoOut", "DefinirPrecoFinal",
    "GerarContratoIn", "ContratoDocumentoOut", "AssinaturaWebhookIn",
]

Formato = Literal["feed", "carrossel", "story", "reels", "video", "artigo"]


class LeadPublicoIn(StrictHttpModel):
    """The public pré-qualificação form.

    `org_id` is a body field because this endpoint is UNAUTHENTICATED — the
    form is embedded on the agency's own site and must say which agency it
    belongs to. It is not a secret and grants nothing on its own.
    """

    org_id: str
    nome: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    empresa: str | None = Field(default=None, max_length=200)
    nicho: str | None = Field(default=None, max_length=120)
    canais_atuais: str | None = Field(default=None, max_length=500)
    dores: str | None = Field(default=None, max_length=2000)
    orcamento_disponivel: float | None = Field(default=None, ge=0)
    origem: str | None = Field(default=None, max_length=120)


class LeadOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    nome: str
    email: str | None = None
    telefone: str | None = None
    empresa: str | None = None
    nicho: str | None = None
    canais_atuais: str | None = None
    dores: str | None = None
    orcamento_disponivel: float | None = None
    origem: str | None = None
    status: str = "novo"
    cliente_id: str | None = None
    created_at: str | None = None


class ItemEscopoIn(StrictHttpModel):
    formato: Formato
    quantidade: int = Field(ge=1, le=1000)
    #: Overrides the default hour estimate when the agency knows better.
    horas_unitarias: float | None = Field(default=None, ge=0)


class EstimativaOut(BaseModel):
    horas: float
    custo: float
    preco_sugerido: float
    custo_hora_medio: float
    margem_alvo: float
    #: Non-empty ⇒ the suggestion is unreliable (missing custo/hora data).
    alertas: list[str] = Field(default_factory=list)


class OrcamentoCreate(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=200)
    itens: list[ItemEscopoIn] = Field(min_length=1)
    lead_id: str | None = None
    cliente_id: str | None = None
    margem_alvo: float = Field(default=50, ge=0, lt=100)


class DefinirPrecoFinal(StrictHttpModel):
    """A director's override of the calculator's suggestion (spec §M1)."""

    preco_final: float = Field(ge=0)


class OrcamentoOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    lead_id: str | None = None
    cliente_id: str | None = None
    titulo: str
    escopo: list[dict] = Field(default_factory=list)
    horas_estimadas: float = 0
    custo_estimado: float = 0
    preco_sugerido: float = 0
    preco_final: float | None = None
    margem_alvo: float = 50
    status: str = "rascunho"


class GerarContratoIn(StrictHttpModel):
    cliente_id: str
    orcamento_id: str | None = None
    titulo: str = Field(default="Contrato de Prestação de Serviços", max_length=200)
    valor_mensal: float = Field(ge=0)
    posts_por_mes: int | None = Field(default=None, ge=0)
    vigencia: str | None = Field(default=None, max_length=120)
    clausulas: list[str] = Field(default_factory=list)
    provedor: Literal["interno", "clicksign", "docusign", "autentique"] = "interno"
    signatario_email: str | None = None


class ContratoDocumentoOut(BaseModel):
    contrato_id: str
    documento_key: str
    provedor: str
    link_assinatura: str
    external_id: str
    #: True ⇒ NO signing vendor was contacted. Surfaced so nobody mistakes a
    #: dry run for a contract actually sent to the client.
    dry_run: bool


class AssinaturaWebhookIn(StrictHttpModel):
    external_id: str
    evento: Literal["assinado", "recusado", "expirado"]
