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

# Rewards (Phase 4)
from app.schemas.rewards import (  # noqa: F401
    AccrualStatus,
    RedemptionOut,
    RedemptionProcessIn,
    RedemptionRequestIn,
    RedemptionStatus,
    RewardLedgerEntry,
    RewardLedgerOut,
    RewardRuleOut,
    RewardRulesListOut,
    RewardType,
)
