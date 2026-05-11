"""
AdConnect Pydantic schemas.

Per-domain modules at `app/schemas/<domain>.py` (identity, catalog, sellout,
rewards). Re-exports here so consumers can do `from app.schemas import X`
rather than `from app.schemas.<domain> import X`.
"""
from __future__ import annotations

# Identity (Phase 1)
from app.schemas.identity import (  # noqa: F401
    DistributorIn,
    DistributorOut,
    MembershipIn,
    MembershipOut,
)

# Catalog (Phase 2)
from app.schemas.catalog import (  # noqa: F401
    CategoriaIn,
    CategoriaOut,
    PrecoDistribuidorIn,
    PrecoDistribuidorOut,
    ProductIn,
    ProductOut,
    PromoIn,
    PromoOut,
)

# Sellout (Phase 4)
from app.schemas.sellout import (  # noqa: F401
    SelloutAttachmentIn,
    SelloutEstruturadoIn,
    SelloutListOut,
    SelloutOut,
    SelloutReviewIn,
    SelloutStatus,
    SubmissionMode,
)

# Rewards (Phase 4) — note: `RewardRuleOut` lives in `app.schemas.admin`
# (single canonical variant; the duplicate in `rewards.py` was deleted
# 2026-05-11 as R1 of the response-model audit).
from app.schemas.rewards import (  # noqa: F401
    AccrualStatus,
    RedemptionOut,
    RedemptionProcessIn,
    RedemptionRequestIn,
    RedemptionStatus,
    RewardLedgerEntry,
    RewardLedgerOut,
    RewardRulesListOut,
    RewardType,
)

# Orders / cart (Phase 3)
from app.schemas.orders import (  # noqa: F401
    CartItemIn,
    CartItemOut,
    CartItemUpdateIn,
    CartOut,
    CartStatus,
    OrderCheckoutIn,
    OrderItemOut,
    OrderListOut,
    OrderOut,
    OrderStatus,
    OrderStatusTransitionIn,
)

# Financial (Phase 5)
from app.schemas.financial import (  # noqa: F401
    CancelRequest,
    FaturaIn,
    FaturaListOut,
    FaturaOut,
    FaturaStatus,
    IssueRequest,
    NFeStatus,
    WebhookEvent,
)

# Admin (Phase 6 — brand-admin V1)
from app.schemas.admin import (  # noqa: F401
    AdminDistributorCreateIn,
    AdminDistributorListOut,
    AdminDistributorPatchIn,
    AdminInvoiceFilters,
    AdminInvoiceListOut,
    AdminSelloutQueueOut,
    DashboardCounts,
    DashboardMetricsOut,
    DistributorMetrics,
    DistributorWithMetricsOut,
    InvoiceStatus,
    RewardRuleIn,
    RewardRuleListOut,
    RewardRuleOut,
    RewardRuleType,
)
