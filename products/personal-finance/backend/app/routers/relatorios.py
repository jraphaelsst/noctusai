"""Reports & analytics router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, Query
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response
from app.services.relatorios_service import RelatoriosService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/relatorios", tags=["Relatorios"])


@router.get("/mensal")
async def relatorio_mensal(
    mes: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = RelatoriosService(db, org_id)
    data = await service.relatorio_mensal(mes)
    return success_response(data)


@router.get("/anual")
async def relatorio_anual(
    ano: str = Query(..., pattern=r"^\d{4}$"),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = RelatoriosService(db, org_id)
    data = await service.relatorio_anual(ano)
    return success_response(data)


@router.get("/fluxo-caixa")
async def fluxo_caixa(
    data_inicio: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    data_fim: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = RelatoriosService(db, org_id)
    data = await service.fluxo_caixa(data_inicio, data_fim)
    return success_response(data)
