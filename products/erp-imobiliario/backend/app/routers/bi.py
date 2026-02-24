"""
Dashboard BI Router — Business Intelligence analytics endpoints.

Read-only endpoints that aggregate data from existing tables for
dashboard visualizations. No new tables required.

Tables consumed: ativos, clientes, lancamentos, propostas, comissoes,
contratos_locacao, contratos.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user, get_user_client
from app.responses import success_response
from app.services.bi_service import BIService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bi", tags=["BI"])


# --- Endpoints ---

@router.get("/vendas")
async def analytics_vendas(
    periodo_inicio: Optional[str] = Query(None, description="Data inicio (YYYY-MM-DD)"),
    periodo_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    authorization: Optional[str] = Header(None),
):
    """Sales analytics: total sales, average ticket, conversion rate, avg close time, monthly breakdown."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch proposals
    propostas_result = db.table("propostas").select("*").execute()
    propostas = propostas_result.data or []

    # Fetch financial transactions (for revenue correlation)
    lancamentos_result = db.table("lancamentos").select("*").execute()
    lancamentos = lancamentos_result.data or []

    analytics = service.get_vendas_analytics(propostas, lancamentos, periodo_inicio, periodo_fim)
    return success_response(analytics)


@router.get("/captacao")
async def analytics_captacao(
    authorization: Optional[str] = Header(None),
):
    """Lead acquisition metrics: total leads, by origin, monthly trend, conversion by origin."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch all clients
    clientes_result = db.table("clientes").select("*").execute()
    clientes = clientes_result.data or []

    analytics = service.get_captacao_analytics(clientes)
    return success_response(analytics)


@router.get("/corretores")
async def analytics_corretores(
    periodo: Optional[str] = Query(None, description="Periodo: '30d', '90d', '6m', '1a' ou 'total'"),
    authorization: Optional[str] = Header(None),
):
    """Broker performance ranking: sales count, total value, commissions, conversion rate."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch proposals (optionally filtered by period)
    propostas_query = db.table("propostas").select("*")
    periodo_inicio = _resolve_periodo(periodo)
    if periodo_inicio:
        propostas_query = propostas_query.gte("created_at", periodo_inicio)
    propostas_result = propostas_query.execute()
    propostas = propostas_result.data or []

    # Fetch commissions
    comissoes_result = db.table("comissoes").select("*").execute()
    comissoes = comissoes_result.data or []

    analytics = service.get_corretores_analytics(propostas, comissoes)
    return success_response(analytics)


@router.get("/imoveis")
async def analytics_imoveis(
    authorization: Optional[str] = Header(None),
):
    """Property portfolio analytics: totals, avg days on market, price/sqm, distributions."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch all properties
    ativos_result = db.table("ativos").select("*").execute()
    ativos = ativos_result.data or []

    analytics = service.get_imoveis_analytics(ativos)
    return success_response(analytics)


@router.get("/financeiro")
async def analytics_financeiro(
    periodo_inicio: Optional[str] = Query(None, description="Data inicio (YYYY-MM-DD)"),
    periodo_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    authorization: Optional[str] = Header(None),
):
    """Financial overview: revenue, expenses, balance, forecast, breakdowns by category and month."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch financial transactions
    lancamentos_result = db.table("lancamentos").select("*").execute()
    lancamentos = lancamentos_result.data or []

    analytics = service.get_financeiro_analytics(lancamentos, periodo_inicio, periodo_fim)
    return success_response(analytics)


# --- Helpers ---

def _resolve_periodo(periodo: Optional[str]) -> Optional[str]:
    """
    Convert a human-friendly period label to a start date string (YYYY-MM-DD).

    Supported values: '30d', '90d', '6m', '1a', 'total' (or None).
    Returns None for 'total' or unrecognized values (no filtering).
    """
    if not periodo or periodo == "total":
        return None

    from datetime import datetime, timedelta

    now = datetime.utcnow()

    if periodo == "30d":
        start = now - timedelta(days=30)
    elif periodo == "90d":
        start = now - timedelta(days=90)
    elif periodo == "6m":
        start = now - timedelta(days=180)
    elif periodo == "1a":
        start = now - timedelta(days=365)
    else:
        return None

    return start.strftime("%Y-%m-%d")
