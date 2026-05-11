"""
Dashboard BI Router — Business Intelligence analytics endpoints.

Read-only endpoints that aggregate data from existing tables for
dashboard visualizations. No new tables required.

Tables consumed: ativos, clientes, lancamentos, propostas, comissoes,
contratos_locacao, contratos.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query
from app.dependencies import get_current_user, get_user_client
from app.responses import success_response
from app.services.bi_service import BIService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bi", tags=["BI"])


# --- Endpoints ---

@router.get("/vendas")
async def analytics_vendas(
    periodo_inicio: Optional[str] = Query(None, description="Data inicio (YYYY-MM-DD)"),
    periodo_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    auth = Depends(get_current_user)):
    """Sales analytics: total sales, average ticket, conversion rate, avg close time, monthly breakdown."""
    user, token = auth
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
    auth = Depends(get_current_user)):
    """Lead acquisition metrics: total leads, by origin, monthly trend, conversion by origin."""
    user, token = auth
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
    auth = Depends(get_current_user)):
    """Broker performance ranking: sales count, total value, commissions, conversion rate."""
    user, token = auth
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
    auth = Depends(get_current_user)):
    """Property portfolio analytics: totals, avg days on market, price/sqm, distributions."""
    user, token = auth
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
    auth = Depends(get_current_user)):
    """Financial overview: revenue, expenses, balance, forecast, breakdowns by category and month."""
    user, token = auth
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Fetch financial transactions
    lancamentos_result = db.table("lancamentos").select("*").execute()
    lancamentos = lancamentos_result.data or []

    analytics = service.get_financeiro_analytics(lancamentos, periodo_inicio, periodo_fim)
    return success_response(analytics)


@router.get("/dashboard")
async def dashboard_resumo(
    auth = Depends(get_current_user)):
    """
    Comprehensive dashboard summary — aggregates key metrics from all modules.

    Returns a single payload with: sales KPIs, funnel stats, financial summary,
    property portfolio counts, pending tasks, and recent activity.
    """
    user, token = auth
    db = get_user_client(token)

    service = BIService(db, user.id)

    # Limit dashboard queries to current year for performance
    year_start = datetime.now(timezone.utc).strftime("%Y-01-01")

    # Fetch data in sequence (Supabase client is sync)
    clientes = (db.table("clientes").select("id, etapa_atual, created_at, valor_estimado").gte("created_at", year_start).execute()).data or []
    ativos = (db.table("ativos").select("id, natureza, status, valor").execute()).data or []
    propostas = (db.table("propostas").select("id, status, valor_proposta, created_at").gte("created_at", year_start).execute()).data or []
    lancamentos = (db.table("lancamentos").select("id, tipo, status, valor, data_vencimento").gte("created_at", year_start).execute()).data or []
    contratos = (db.table("contratos").select("id, status, valor_total").gte("created_at", year_start).execute()).data or []
    eventos = (db.table("eventos").select("id, status, data_inicio").gte("created_at", year_start).execute()).data or []
    negociacoes = (db.table("negociacoes").select("id, status_etapa").gte("created_at", year_start).execute()).data or []

    resumo = service.get_dashboard_resumo(
        clientes, ativos, propostas, lancamentos, contratos, eventos, negociacoes,
    )

    return success_response(resumo)


# --- Helpers ---

def _resolve_periodo(periodo: Optional[str]) -> Optional[str]:
    """
    Convert a human-friendly period label to a start date string (YYYY-MM-DD).

    Supported values: '30d', '90d', '6m', '1a', 'total' (or None).
    Returns None for 'total' or unrecognized values (no filtering).
    """
    if not periodo or periodo == "total":
        return None

    now = datetime.now(timezone.utc)

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
