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


@router.get("/dashboard")
async def dashboard_resumo(
    authorization: Optional[str] = Header(None),
):
    """
    Comprehensive dashboard summary — aggregates key metrics from all modules.

    Returns a single payload with: sales KPIs, funnel stats, financial summary,
    property portfolio counts, pending tasks, and recent activity.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch data in sequence (Supabase client is sync)
    clientes_result = db.table("clientes").select("id, etapa_funil, created_at, valor_estimado").execute()
    clientes = clientes_result.data or []

    ativos_result = db.table("ativos").select("id, natureza, status, valor").execute()
    ativos = ativos_result.data or []

    propostas_result = db.table("propostas").select("id, status, valor_proposta, created_at").execute()
    propostas = propostas_result.data or []

    lancamentos_result = db.table("lancamentos").select("id, tipo, status, valor, data_vencimento").execute()
    lancamentos = lancamentos_result.data or []

    contratos_result = db.table("contratos").select("id, status, valor_total").execute()
    contratos = contratos_result.data or []

    eventos_result = db.table("eventos").select("id, status, data_inicio").execute()
    eventos = eventos_result.data or []

    negociacoes_result = db.table("negociacoes").select("id, status").execute()
    negociacoes = negociacoes_result.data or []

    # ── KPIs ──
    total_clientes = len(clientes)
    clientes_novos_mes = sum(
        1 for c in clientes
        if (c.get("created_at") or "")[:7] == datetime.now(timezone.utc).strftime("%Y-%m")
    )

    imoveis_ativos = sum(1 for a in ativos if a.get("natureza") == "imovel" and a.get("status") == "ativo")
    total_imoveis = sum(1 for a in ativos if a.get("natureza") == "imovel")

    propostas_abertas = sum(1 for p in propostas if p.get("status") in ("rascunho", "enviada"))
    propostas_aceitas = sum(1 for p in propostas if p.get("status") == "aceita")
    valor_vendas = sum(float(p.get("valor_proposta", 0)) for p in propostas if p.get("status") == "aceita")

    # ── Funil ──
    etapas_funil = {}
    for c in clientes:
        etapa = c.get("etapa_funil") or "sem_etapa"
        etapas_funil[etapa] = etapas_funil.get(etapa, 0) + 1

    # ── Financeiro ──
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mes_atual = datetime.now(timezone.utc).strftime("%Y-%m")

    receitas_mes = sum(
        float(l.get("valor", 0)) for l in lancamentos
        if l.get("tipo") == "receita" and l.get("status") == "pago"
        and (l.get("data_vencimento") or "")[:7] == mes_atual
    )
    despesas_mes = sum(
        float(l.get("valor", 0)) for l in lancamentos
        if l.get("tipo") == "despesa" and l.get("status") == "pago"
        and (l.get("data_vencimento") or "")[:7] == mes_atual
    )
    vencidos = sum(
        1 for l in lancamentos
        if l.get("status") == "pendente" and (l.get("data_vencimento") or "") < hoje
    )
    a_receber = sum(
        float(l.get("valor", 0)) for l in lancamentos
        if l.get("tipo") == "receita" and l.get("status") == "pendente"
    )

    # ── Contratos ──
    contratos_ativos = sum(1 for c in contratos if c.get("status") == "ativo")

    # ── Agenda ──
    eventos_hoje = sum(
        1 for e in eventos
        if (e.get("data_inicio") or "")[:10] == hoje and e.get("status") == "agendado"
    )

    # ── Negociações ──
    negociacoes_abertas = sum(1 for n in negociacoes if n.get("status") in ("aberta", "em_andamento"))

    return success_response({
        "kpis": {
            "total_clientes": total_clientes,
            "clientes_novos_mes": clientes_novos_mes,
            "imoveis_ativos": imoveis_ativos,
            "total_imoveis": total_imoveis,
            "propostas_abertas": propostas_abertas,
            "propostas_aceitas": propostas_aceitas,
            "valor_vendas": round(valor_vendas, 2),
            "contratos_ativos": contratos_ativos,
            "negociacoes_abertas": negociacoes_abertas,
            "eventos_hoje": eventos_hoje,
        },
        "funil": etapas_funil,
        "financeiro": {
            "receitas_mes": round(receitas_mes, 2),
            "despesas_mes": round(despesas_mes, 2),
            "saldo_mes": round(receitas_mes - despesas_mes, 2),
            "a_receber": round(a_receber, 2),
            "vencidos": vencidos,
        },
    })


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
