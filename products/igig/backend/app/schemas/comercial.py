"""Contracts for Módulo 1 — leads and the signature webhook.

Orçamento / catálogo / contrato contracts are `app/schemas/orcamento.py`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = ["LeadPublicoIn", "LeadOut", "AssinaturaWebhookIn"]


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
    #: "Como nos conheceu" — free text, kept under this name so the embedded
    #: form's contract is unchanged; stored as `lead.como_conheceu` (018).
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
    #: The CHANNEL: formulario | manual | whatsapp | meta_ads (migration 018).
    origem: str | None = None
    #: The public form's free-text "como nos conheceu".
    como_conheceu: str | None = None
    instagram: str | None = None
    especificacoes: dict = Field(default_factory=dict)
    observacoes: str | None = None
    status: str = "novo"
    cliente_id: str | None = None
    created_at: str | None = None


class AssinaturaWebhookIn(StrictHttpModel):
    external_id: str
    evento: Literal["assinado", "recusado", "expirado"]
