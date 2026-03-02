"""Real-time stock quotes router."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Header, Query
from pydantic import BaseModel
from app.dependencies import get_current_user, get_current_user_org, get_user_client
from app.responses import success_response
from app.services.cotacoes_service import CotacoesService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cotacoes", tags=["Cotacoes"])


class BatchRequest(BaseModel):
    tickers: List[str]


@router.get("/{ticker}")
async def obter_cotacao(ticker: str, authorization: Optional[str] = Header(None)):
    await get_current_user(authorization)
    service = CotacoesService()
    data = await service.get_cotacao(ticker)
    return success_response(data)


@router.post("/batch")
async def cotacoes_batch(body: BatchRequest, authorization: Optional[str] = Header(None)):
    await get_current_user(authorization)
    service = CotacoesService()
    data = await service.get_cotacoes_batch(body.tickers)
    return success_response(data)


@router.post("/atualizar")
async def atualizar_precos(
    carteira_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """Update holdings with current market prices. If carteira_id is given, update only that portfolio."""
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    service = CotacoesService(db, org_id)

    if carteira_id:
        data = await service.atualizar_precos_carteira(carteira_id)
    else:
        data = await service.atualizar_todos()

    return success_response(data)
