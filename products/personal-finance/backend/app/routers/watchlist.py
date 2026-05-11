"""Stock watchlist router."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response, ok_response
from app.schemas.watchlist import WatchlistCreate, WatchlistItemCreate
from app.services.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlists", tags=["Watchlists"])


@router.get("")
async def listar_watchlists(auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    data = await service.listar()
    return success_response(data, total=len(data))


@router.get("/{watchlist_id}")
async def obter_watchlist(watchlist_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    data = await service.obter(watchlist_id)
    return success_response(data)


@router.post("")
async def criar_watchlist(body: WatchlistCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    data = await service.criar(body.model_dump())
    return success_response(data)


@router.delete("/{watchlist_id}")
async def excluir_watchlist(watchlist_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    await service.excluir(watchlist_id)
    return ok_response("Watchlist excluida com sucesso")


@router.post("/{watchlist_id}/itens")
async def adicionar_item(watchlist_id: str, body: WatchlistItemCreate, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    data = await service.adicionar_item(watchlist_id, body.model_dump(exclude_none=True))
    return success_response(data)


@router.delete("/itens/{item_id}")
async def remover_item(item_id: str, auth: tuple = Depends(get_current_user_org)):
    user, token, org_id = auth
    db = get_user_client(token)
    service = WatchlistService(db, org_id)
    await service.remover_item(item_id)
    return ok_response("Item removido com sucesso")
