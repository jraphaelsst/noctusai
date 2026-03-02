"""Dashboard KPIs and aggregated data router."""
import logging
from typing import Optional
from datetime import date
from fastapi import APIRouter, Header
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response
from app.services.patrimonio_service import PatrimonioService
from app.services.relatorios_service import RelatoriosService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def dashboard_kpis(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    # Net worth
    patrimonio_service = PatrimonioService(db, org_id)
    patrimonio = await patrimonio_service.calcular_atual()

    # Monthly cash flow
    hoje = date.today()
    mes_atual = f"{hoje.year}-{hoje.month:02d}"
    relatorio_service = RelatoriosService(db, org_id)
    mensal = await relatorio_service.relatorio_mensal(mes_atual)

    # Investment return (sum of gain/loss across all holdings)
    ativos = db.table("ativos").select("ganho_perda,valor_atual").eq("org_id", org_id).execute()
    holdings = ativos.data or []
    retorno_investimentos = sum(float(a.get("ganho_perda", 0)) for a in holdings)
    valor_investimentos = sum(float(a.get("valor_atual", 0)) for a in holdings)

    return success_response({
        "patrimonio_liquido": patrimonio.get("patrimonio_liquido", 0),
        "total_ativos": patrimonio.get("total_ativos", 0),
        "total_passivos": patrimonio.get("total_passivos", 0),
        "receita_mensal": mensal.get("receita_total", 0),
        "despesa_mensal": mensal.get("despesa_total", 0),
        "fluxo_caixa_mensal": mensal.get("fluxo_liquido", 0),
        "taxa_poupanca": mensal.get("taxa_poupanca", 0),
        "retorno_investimentos": round(retorno_investimentos, 2),
        "valor_investimentos": round(valor_investimentos, 2),
    })


@router.get("/resumo")
async def dashboard_resumo(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    hoje = date.today()

    # Recent transactions
    transacoes = db.table("transacoes").select("*, conta:contas!transacoes_conta_id_fkey(id,nome,cor), categoria:categorias(id,nome,icone,cor)").eq("org_id", org_id).order("data", desc=True).limit(5).execute()

    # Upcoming bills
    from datetime import timedelta
    limite = (hoje + timedelta(days=7)).isoformat()
    proximas = db.table("recorrentes").select("*, categoria:categorias(id,nome,icone,cor)").eq("org_id", org_id).eq("ativo", True).gte("proxima_data", hoje.isoformat()).lte("proxima_data", limite).order("proxima_data").execute()

    # Active goals
    metas = db.table("metas").select("*").eq("org_id", org_id).eq("status", "ativa").order("prioridade").limit(5).execute()
    metas_data = metas.data or []
    for meta in metas_data:
        valor_alvo = float(meta.get("valor_alvo", 1))
        valor_atual = float(meta.get("valor_atual", 0))
        meta["percentual"] = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)

    return success_response({
        "transacoes_recentes": transacoes.data or [],
        "proximas_contas": proximas.data or [],
        "metas_ativas": metas_data,
    })
