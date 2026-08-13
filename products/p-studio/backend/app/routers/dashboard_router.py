"""Dashboard executivo (spec § 1) e métricas por cliente (spec § 8)."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, get_current_user
from app.schemas.clientes import ClienteMetricas
from app.schemas.dashboard import DashboardOut
from app.services.dashboard_service import ClienteMetricasService, DashboardService

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser = Depends(get_current_user)):
    return DashboardService(user.db, user.org_id).montar()


@router.get("/clientes-metricas", response_model=list[ClienteMetricas])
def clientes_metricas(user: CurrentUser = Depends(get_current_user)):
    """Histórico consolidado por cliente: faturamento, serviços, imóveis,
    ticket médio, último serviço e frequência de contratação."""
    return ClienteMetricasService(user.db, user.org_id).metricas()
