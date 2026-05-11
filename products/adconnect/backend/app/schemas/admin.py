"""
Pydantic schemas for the brand-admin V1 surface (Phase 6).

Brand admin gets cross-cutting visibility — distributors-with-metrics, dashboard
aggregates, sellout review queue, reward-rule CRUD, cross-distributor invoice
filters. The DB column inventory lives in `migrations/001_adconnect.sql` under
the relevant section.

The `RewardRuleIn / RewardRuleOut` shapes mirror `adconnect.regras_recompensa`
and replace the legacy mock-backed `RewardRuleInput` from the prior admin.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel

from app.schemas.identity import DistributorIn

RewardRuleType = Literal["cashback_percentual", "cashback_fixo", "pontos"]
InvoiceStatus = Literal[
    "rascunho", "emitida", "paga", "vencida", "cancelada", "estornada"
]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardCounts(StrictHttpModel):
    """Counts/aggregations bucket — keeps the dashboard payload self-describing."""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)


class DashboardMetricsOut(StrictHttpModel):
    """Single-call dashboard payload for the brand admin landing.

    Aggregates across distributors + pedidos (this calendar month) + sellout +
    rewards + invoices. The shape stays denormalized on purpose — one HTTP
    round-trip beats five for a dashboard.
    """

    distributors: DashboardCounts
    pedidos_this_month: DashboardCounts
    sellout: DashboardCounts
    recompensas: DashboardCounts  # accumulated reward total + by-status
    faturas: DashboardCounts


# ---------------------------------------------------------------------------
# Distributor list with metrics
# ---------------------------------------------------------------------------


class DistributorMetrics(StrictHttpModel):
    """Per-distributor aggregations the admin list view surfaces."""

    last_pedido_at: Optional[datetime] = None
    total_pedidos: int = 0
    recompensa_balance: float = 0.0
    invoices_pending: int = 0


class DistributorWithMetricsOut(StrictHttpModel):
    """Distributor row + per-row aggregations.

    Mirrors `DistributorOut` shape from `app.schemas.identity`, plus `metrics`.
    Deliberate carve-out from `StrictHttpModel` strictness: keeps `extra="allow"`
    so unexpected DB columns surface in the response without a 422 — admin V2
    can lock this down once the UI shape is final. The carve-out is the
    canonical example referenced in `seed/lib/backend/noctusai_lib/api/schemas.py`.
    """

    # Explicit opt-out from the StrictHttpModel parent default of extra="forbid".
    model_config = ConfigDict(extra="allow")

    id: str
    org_id: str
    cnpj: str
    nome: str
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = None
    contato_email: Optional[str] = None
    contato_telefone: Optional[str] = None
    status: str
    tier: str
    created_at: Optional[datetime] = None
    metrics: DistributorMetrics = Field(default_factory=DistributorMetrics)


# ---------------------------------------------------------------------------
# Reward rules (CRUD payloads — replaces legacy RewardRuleInput)
# ---------------------------------------------------------------------------


class RewardRuleIn(StrictHttpModel):
    """Brand-admin payload to create or update a reward rule.

    Mirrors `adconnect.regras_recompensa` columns. The router fills `org_id`
    from the caller's JWT, so the input does not carry it.
    """

    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    tipo: RewardRuleType
    valor: float = Field(..., gt=0)
    aplicavel_categorias: list[str] = Field(default_factory=list)
    aplicavel_produtos: list[str] = Field(default_factory=list)
    aplicavel_distribuidores: list[str] = Field(default_factory=list)
    valor_minimo_pedido: Optional[float] = None
    quantidade_minima: Optional[int] = None
    valido_de: Optional[datetime] = None
    valido_ate: Optional[datetime] = None
    ativa: bool = True


class RewardRuleOut(RewardRuleIn):
    id: str
    org_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RewardRuleListOut(StrictHttpModel):
    """Loose list-shape — DB-row dicts pass through verbatim. Strict
    `RewardRuleOut` validation lives at the create/update endpoints where
    the response always carries the full shape; at list-time we keep the
    response permissive so partial / migrated rows don't 500."""

    data: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Invoice cross-filter
# ---------------------------------------------------------------------------


class AdminInvoiceFilters(StrictHttpModel):
    """Query-string filters for `GET /api/admin/invoices`.

    Kept on a Pydantic model rather than as bare router kwargs so the same
    shape can be reused for the admin V2 UI form binding without redefinition.
    The router still accepts them as `Query(...)` params (Pydantic-as-DTO,
    not as request body) — see `app/routers/admin.py`.
    """

    status: Optional[InvoiceStatus] = None
    distributor_id: Optional[str] = None
    due_from: Optional[str] = None  # ISO date
    due_to: Optional[str] = None


class AdminDistributorListOut(StrictHttpModel):
    data: list[DistributorWithMetricsOut] = Field(default_factory=list)


class AdminInvoiceListOut(StrictHttpModel):
    data: list[dict[str, Any]] = Field(default_factory=list)


class AdminSelloutQueueOut(StrictHttpModel):
    data: list[dict[str, Any]] = Field(default_factory=list)


class AdminDistributorCreateIn(DistributorIn):
    """Brand-admin create payload — adds the seam for the membership invitation
    flow if/when admin wants to create the distributor + invite owner in one
    POST. V1 keeps creation only; the membership/invite step is a follow-up."""


class AdminDistributorPatchIn(StrictHttpModel):
    """Brand-admin patch payload — every field optional, only provided fields
    update. Mirrors the columns brand admin V1 surfaces; locked fields (id,
    org_id, created_at) are excluded."""

    cnpj: Optional[str] = None
    nome: Optional[str] = None
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = Field(default=None, max_length=2)
    endereco_cep: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_email: Optional[str] = None
    contato_telefone: Optional[str] = None
    status: Optional[str] = None
    tier: Optional[str] = None


__all__ = [
    "DashboardCounts",
    "DashboardMetricsOut",
    "DistributorMetrics",
    "DistributorWithMetricsOut",
    "RewardRuleIn",
    "RewardRuleOut",
    "RewardRuleListOut",
    "AdminInvoiceFilters",
    "AdminInvoiceListOut",
    "AdminSelloutQueueOut",
    "AdminDistributorListOut",
    "AdminDistributorCreateIn",
    "AdminDistributorPatchIn",
    "RewardRuleType",
    "InvoiceStatus",
]
