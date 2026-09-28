"""Dashboard router — CONTRACT.md §Cashflow + dashboard, slice BE-C.

Auth: `Depends(get_current_user_org)` (401 boundary). Staff-only route —
no `require_admin` gate: both `admin` and `moderador` may read (same
posture as `GET /api/membros`, `GET /api/assinaturas`).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.dependencies import coerce_org_uuid, get_current_user_org, get_user_client
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    meses: int = Query(default=12, ge=1, le=24),
    auth: tuple = Depends(get_current_user_org),
) -> DashboardResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = DashboardService(client, org_id=org_id)
    result = await service.build(meses=meses)
    return DashboardResponse(**result)
