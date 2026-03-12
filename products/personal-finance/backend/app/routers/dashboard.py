"""Dashboard KPIs and aggregated data router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def dashboard_kpis(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = DashboardService(db, org_id)
    return success_response(await service.kpis())


@router.get("/resumo")
async def dashboard_resumo(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = DashboardService(db, org_id)
    return success_response(await service.resumo())
