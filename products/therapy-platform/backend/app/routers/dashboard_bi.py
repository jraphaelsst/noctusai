"""
Dashboard BI Router — Business intelligence and analytics.

Provides aggregated metrics for therapists: session counts,
revenue breakdowns, cancellation rates, and dashboard summaries.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import success_response
from app.services import bi_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bi", tags=["Dashboard BI"])


@router.get("/resumo")
async def dashboard_summary(
    authorization: Optional[str] = Header(None),
):
    """Get dashboard summary (therapist only).

    Returns key KPIs: total patients, sessions this month, revenue, etc.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem acessar o painel BI")

    db = get_user_client(token)
    data = await bi_service.get_dashboard_resumo(
        therapist_id=user.id,
        db=db,
    )
    return success_response(data)


@router.get("/sessoes")
async def session_metrics(
    authorization: Optional[str] = Header(None),
    periodo: Optional[str] = Query("mensal", description="Período: semanal, mensal, trimestral"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """Get session metrics by period."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem acessar métricas de sessões")

    db = get_user_client(token)
    data = await bi_service.get_sessoes_por_periodo(
        therapist_id=user.id,
        db=db,
        inicio=data_inicio,
        fim=data_fim,
    )
    return success_response(data)


@router.get("/receita")
async def revenue_metrics(
    authorization: Optional[str] = Header(None),
    periodo: Optional[str] = Query("mensal", description="Período: semanal, mensal, trimestral"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """Get revenue metrics by period."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem acessar métricas de receita")

    db = get_user_client(token)
    data = await bi_service.get_receita_por_periodo(
        therapist_id=user.id,
        db=db,
        inicio=data_inicio,
        fim=data_fim,
    )
    return success_response(data)


@router.get("/cancelamentos")
async def cancellation_rates(
    authorization: Optional[str] = Header(None),
    periodo: Optional[str] = Query("mensal", description="Período: semanal, mensal, trimestral"),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """Get cancellation rate metrics."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem acessar taxas de cancelamento")

    db = get_user_client(token)
    data = await bi_service.get_taxa_cancelamento(
        therapist_id=user.id,
        db=db,
    )
    return success_response(data)
