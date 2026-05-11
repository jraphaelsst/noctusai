"""
Pydantic schemas for the rewards router.

`RewardRuleOut` lives in `app.schemas.admin` — that variant inherits from
`RewardRuleIn` and matches the `regras_recompensa` table 1:1 (correct field
names: `valor` not `cashback_pct`, `ativa` not `ativo`; `tipo` Literal
matches the DB CHECK). A duplicate broken `RewardRuleOut` previously lived
here; deleted 2026-05-11 (R1 of `response-model-silent-drop-audit`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel

# Two disjoint `tipo` vocabularies — they correspond to DIFFERENT tables
# and DIFFERENT CHECK constraints. Keeping them split prevents the
# silent-CHECK-violation slip ADCO-REWARDS-STATUS-CHECK fixed (the previous
# unified `RewardType` allowed `'verba_mkt'` against `recompensas_acumuladas`
# which only accepts `cashback`/`pontos`, and rejected the migration's actual
# `'pontos'` ledger value).
#
# - `LedgerRewardType` matches `adconnect.recompensas_acumuladas.tipo` CHECK.
# - `RedemptionRewardType` matches `adconnect.resgates_recompensa.tipo` CHECK
#   (post migration 003 — NULL allowed; treated here as the documented enum).
LedgerRewardType = Literal["cashback", "pontos"]
RedemptionRewardType = Literal["cashback", "verba_mkt"]
# Back-compat alias — historical name kept so any unqualified external import
# (no known consumers in-tree, but the field appeared in router schemas)
# resolves to the redemption-side vocabulary.
RewardType = RedemptionRewardType

# `recompensas_acumuladas.status` CHECK — schema-defined lifecycle.
# `acumulado` = accrual created (the default — what previously was written
#               as `'pendente'`, a value the CHECK never accepted).
# `resgatado` = consumed by a redemption (was `'utilizado'`).
# `expirado`  = past expires_at and not yet redeemed.
AccrualStatus = Literal["acumulado", "resgatado", "expirado"]
RedemptionStatus = Literal["pendente", "aprovado", "rejeitado", "pago"]


class RewardLedgerEntry(StrictHttpModel):
    id: str
    distributor_id: str
    regra_id: Optional[str] = None
    # Ledger uses the recompensas_acumuladas CHECK vocabulary
    # (cashback/pontos), NOT the redemption vocabulary (cashback/verba_mkt).
    tipo: LedgerRewardType
    valor: float
    moeda: str = "BRL"
    source_pedido_id: Optional[str] = None
    source_relatorio_sellout_id: Optional[str] = None
    status: AccrualStatus
    descricao: Optional[str] = None
    accrued_at: Optional[datetime] = None


class RewardLedgerOut(StrictHttpModel):
    data: list[RewardLedgerEntry] = Field(default_factory=list)
    summary: dict[str, float] = Field(default_factory=dict)


class RewardRulesListOut(StrictHttpModel):
    """Loose list-shape — DB-row dicts pass through verbatim, matching the
    `admin.RewardRuleListOut` pattern. Strict validation lives at the
    create/update endpoints (in `app.routers.admin`) which use the
    `admin.RewardRuleOut` shape directly."""

    data: list[dict[str, Any]] = Field(default_factory=list)


class RedemptionRequestIn(StrictHttpModel):
    distributor_id: str
    # Redemptions live in `resgates_recompensa` whose CHECK allows
    # 'cashback' or 'verba_mkt' (the brand can redeem either pool).
    tipo: RedemptionRewardType
    valor: float
    pedido_ref: Optional[str] = None


class RedemptionProcessIn(StrictHttpModel):
    status: Literal["aprovado", "rejeitado", "pago"]
    review_notes: Optional[str] = None


class RedemptionOut(StrictHttpModel):
    """Mirror of `adconnect.resgates_recompensa` post-migration-003.

    Pre-003 fields (schema-declared, added to the table by 003):
      `org_id`, `tipo`, `valor`, `pedido_ref`, `review_notes`,
      `reviewed_by`, `reviewed_at`, `paid_at`, `requested_at`.

    Original-migration fields (kept user-facing in the response):
      `valor_total`, `metodo`, `observacoes`, `created_at`, `processed_at`.
    """

    id: str
    org_id: Optional[str] = None
    distributor_id: str
    tipo: Optional[RedemptionRewardType] = None
    valor: Optional[float] = None
    pedido_ref: Optional[str] = None
    status: RedemptionStatus
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    requested_at: Optional[datetime] = None
    requested_by: Optional[str] = None
    # Columns present in the original migration (pre-003) — kept on the
    # response so the frontend can surface the aggregate, method, free-form
    # notes, and DB-stamp timestamps.
    valor_total: Optional[float] = None
    metodo: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


__all__ = [
    "RewardType",
    "LedgerRewardType",
    "RedemptionRewardType",
    "AccrualStatus",
    "RedemptionStatus",
    "RewardLedgerEntry",
    "RewardLedgerOut",
    "RewardRulesListOut",
    "RedemptionRequestIn",
    "RedemptionProcessIn",
    "RedemptionOut",
]
