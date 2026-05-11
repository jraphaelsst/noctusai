"""Request/response schemas for `app.routers.admin_llm_spend`."""
from __future__ import annotations

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class BudgetUpdate(StrictHttpModel):
    monthly_brl: float = Field(..., ge=0, le=1_000_000)
