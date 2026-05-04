"""Read-only list of `media_scheduling.condominiums`.

Frontend contract (Phase 5 hooks `useAppointments.ts::useCondominiumOptions`):
  - GET /api/condominiums → `{data: [{id, name}, ...]}`

Powers the condominium dropdown on the appointments-filter bar. Returns
ALL active condominiums (small static catalog — under 100 rows
expected). When the catalog grows, switch to paginated; for now keep
the contract simple.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException

from app.database import get_supabase_client
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/condominiums", tags=["Condominiums"])


@router.get("")
async def list_condominiums(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    try:
        result = (
            db.table("condominiums")
            .select("id, name")
            .eq("active", True)
            .order("name", desc=False)
            .execute()
        )
    except Exception as exc:
        logger.warning("condominiums list failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": result.data or []}
