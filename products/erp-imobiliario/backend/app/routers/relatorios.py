"""
Relatorios (Reports) Router — Advanced reporting endpoints for the ERP.

Provides agent ranking, funnel conversion rates, monthly activity reports,
and CSV export.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_user, get_user_client
from app.responses import success_response
from app.services.relatorios_service import (
    ranking_corretores,
    conversao_funil,
    atividade_mensal,
    generate_csv,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/relatorios", tags=["Relatórios"])


def _get_org_id(user) -> str:
    """Extract org_id from user metadata."""
    org_id = user.user_metadata.get("org_id") if user.user_metadata else None
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Usuário sem organização associada")
    return org_id


@router.get("/ranking-corretores")
async def get_ranking_corretores(
    periodo: int = Query(30, ge=1, le=365, description="Período em dias"),
    authorization: Optional[str] = Header(None),
):
    """
    Agent ranking by sales, commissions, and active clients.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = _get_org_id(user)

    data = ranking_corretores(
        org_id=org_id,
        supabase=db,
        periodo_dias=periodo,
    )
    return success_response(data)


@router.get("/conversao-funil")
async def get_conversao_funil(
    authorization: Optional[str] = Header(None),
):
    """
    Funnel conversion rates between pipeline stages.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = _get_org_id(user)

    data = conversao_funil(
        org_id=org_id,
        supabase=db,
    )
    return success_response(data)


@router.get("/atividade-mensal")
async def get_atividade_mensal(
    meses: int = Query(6, ge=1, le=24, description="Número de meses"),
    authorization: Optional[str] = Header(None),
):
    """
    Monthly activity report (actions, new clients, sales).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = _get_org_id(user)

    data = atividade_mensal(
        org_id=org_id,
        supabase=db,
        meses=meses,
    )
    return success_response(data)


@router.get("/export/csv")
async def export_csv(
    tipo: str = Query(
        ...,
        description="Tipo de relatório: ranking-corretores, conversao-funil, atividade-mensal",
    ),
    periodo: int = Query(30, ge=1, le=365),
    meses: int = Query(6, ge=1, le=24),
    authorization: Optional[str] = Header(None),
):
    """
    Export report data as a CSV file.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = _get_org_id(user)

    if tipo == "ranking-corretores":
        data = ranking_corretores(org_id=org_id, supabase=db, periodo_dias=periodo)
        headers = ["nome", "email", "total_clientes", "clientes_fechados",
                    "valor_total_fechados", "total_atividades"]
        filename = "ranking_corretores.csv"
    elif tipo == "conversao-funil":
        data = conversao_funil(org_id=org_id, supabase=db)
        headers = ["etapa", "label", "total", "taxa_conversao"]
        filename = "conversao_funil.csv"
    elif tipo == "atividade-mensal":
        data = atividade_mensal(org_id=org_id, supabase=db, meses=meses)
        headers = ["mes", "total_atividades", "novos_clientes", "fechados"]
        filename = "atividade_mensal.csv"
    else:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de relatório inválido: {tipo}. "
                   "Use ranking-corretores, conversao-funil ou atividade-mensal.",
        )

    csv_content = generate_csv(data, headers)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
