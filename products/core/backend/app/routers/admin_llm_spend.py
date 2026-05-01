"""Per-org LLM-spend status endpoint — Phase 18 (X4).

  - GET /api/admin/llm-spend/{org_id}    → status dict from compute_budget_status
  - PUT /api/admin/llm-spend/{org_id}/budget {monthly_brl: float}
        → upsert org_settings.monthly_llm_budget_brl

Both gated behind `get_current_admin` (platform admin only). Org owners
will get a per-org variant in a follow-up; for now only platform admin
can set the budget.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from noctusai_lib.integrations.llm.budget import compute_status

from app.database import get_admin_client
from app.dependencies import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/llm-spend", tags=["Admin · LLM Spend"])


class BudgetUpdate(BaseModel):
    monthly_brl: float = Field(..., ge=0, le=1_000_000)


@router.get("/{org_id}")
async def get_spend_status(
    org_id: str, authorization: Optional[str] = Header(None)
):
    """Return `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}`."""
    await get_current_admin(authorization)
    status = await compute_status(org_id)
    return {"data": {**status, "org_id": org_id}}


@router.put("/{org_id}/budget")
async def update_budget(
    org_id: str,
    body: BudgetUpdate,
    authorization: Optional[str] = Header(None),
):
    """Upsert `org_settings.monthly_llm_budget_brl` for the org. Pass 0 to
    clear (returns guard to fail-open / unlimited)."""
    await get_current_admin(authorization)
    db = get_admin_client()
    try:
        db.table("org_settings").upsert(
            {
                "org_id": org_id,
                "key": "monthly_llm_budget_brl",
                "value": str(body.monthly_brl),
            },
            on_conflict="org_id,key",
        ).execute()
    except Exception as e:
        logger.error("admin_llm_spend.update_budget failed for org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Erro ao atualizar orçamento")
    return {"data": {"org_id": org_id, "monthly_brl": body.monthly_brl, "ok": True}}
