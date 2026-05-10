"""
Pydantic schemas for the financial router (Phase 5 — Supabase-backed).

Tables (see `migrations/001_adconnect.sql` § 7 FINANCIAL):
  • adconnect.faturas — invoice with NF-e xml + Stripe invoice_id

Lifecycle (single status column; service-layer enforces transitions):
  rascunho → emitida → paga / vencida / cancelada / estornada

NF-e status (independent column, follows Brazilian provider lifecycle):
  pendente → enviado → autorizado → cancelado
                    └→ rejeitado
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

FaturaStatus = Literal[
    "rascunho",
    "emitida",
    "paga",
    "vencida",
    "cancelada",
    "estornada",
]
NFeStatus = Literal[
    "pendente",
    "enviado",
    "autorizado",
    "rejeitado",
    "cancelado",
]


# ---------------------------------------------------------------------------
# Faturas
# ---------------------------------------------------------------------------


class FaturaIn(BaseModel):
    """Body for `POST /financial/invoices` — creates a draft invoice for a pedido.

    Phase 5 wires this from the order-confirmed lifecycle: when admin
    transitions a pedido to `confirmado`, a draft fatura is generated. The
    explicit POST surface is provided so the brand admin can also create
    a fatura manually (one-off charges, adjustments).
    """

    pedido_id: str
    due_date: Optional[date] = None
    observacoes: Optional[str] = None


class FaturaOut(BaseModel):
    id: str
    distributor_id: str
    pedido_id: Optional[str] = None
    numero_fatura: str
    valor_total: float
    moeda: str = "BRL"
    # NF-e fields:
    nfe_xml: Optional[str] = None
    nfe_xml_url: Optional[str] = None
    nfe_chave: Optional[str] = None
    nfe_status: NFeStatus = "pendente"
    nfe_provider: Optional[str] = None
    nfe_provider_id: Optional[str] = None
    # Stripe fields:
    stripe_invoice_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    # Lifecycle:
    status: FaturaStatus
    issued_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    due_date: Optional[date] = None
    canceled_at: Optional[datetime] = None
    observacoes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FaturaListOut(BaseModel):
    data: list[FaturaOut] = Field(default_factory=list)


class IssueRequest(BaseModel):
    """Body for `POST /financial/invoices/{id}/issue` — admin issues NF-e + Stripe invoice."""

    # Optional override of due_date when issuing.
    due_date: Optional[date] = None


class CancelRequest(BaseModel):
    """Body for `POST /financial/invoices/{id}/cancel` — requires justificativa per NF-e regulation."""

    justificativa: str = Field(min_length=15, max_length=255)


class WebhookEvent(BaseModel):
    """Stripe webhook event envelope (subset we care about)."""

    id: str
    type: str
    data: dict


__all__ = [
    "FaturaStatus",
    "NFeStatus",
    "FaturaIn",
    "FaturaOut",
    "FaturaListOut",
    "IssueRequest",
    "CancelRequest",
    "WebhookEvent",
]
