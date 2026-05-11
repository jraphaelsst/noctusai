"""Net worth tracking router."""
import logging
from typing import Optional
from fastapi import APIRouter, Query, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response
from app.services.patrimonio_service import PatrimonioService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/patrimonio", tags=["Patrimonio"])


@router.get("/atual")
async def patrimonio_atual(auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = PatrimonioService(db, org_id)
    data = await service.calcular_atual()
    return success_response(data)


@router.get("/historico")
async def patrimonio_historico(
    limite: int = Query(24, ge=1, le=120),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = PatrimonioService(db, org_id)
    data = await service.historico(limite=limite)
    return success_response(data, total=len(data))


@router.post("/snapshot")
async def criar_snapshot(
    data_snapshot: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = PatrimonioService(db, org_id)
    data = await service.criar_snapshot(data_snapshot)
    return success_response(data)
