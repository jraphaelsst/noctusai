"""Stock watchlist router."""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from app.dependencies import get_current_user_org, get_user_client, first_or_none
from app.responses import success_response, ok_response
from app.schemas.relatorios import WatchlistCreate, WatchlistItemCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlists", tags=["Watchlists"])


@router.get("")
async def listar_watchlists(authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("watchlists").select("*").eq("org_id", org_id).order("created_at").execute()
    return success_response(result.data or [], total=len(result.data or []))


@router.get("/{watchlist_id}")
async def obter_watchlist(watchlist_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("watchlists").select("*").eq("id", watchlist_id).eq("org_id", org_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist nao encontrada")

    itens = db.table("watchlist_itens").select("*").eq("watchlist_id", watchlist_id).order("created_at").execute()
    result.data["itens"] = itens.data or []
    return success_response(result.data)


@router.post("")
async def criar_watchlist(body: WatchlistCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    data = body.model_dump()
    data["org_id"] = org_id
    result = db.table("watchlists").insert(data).execute()
    row = first_or_none(result)
    return success_response(row)


@router.delete("/{watchlist_id}")
async def excluir_watchlist(watchlist_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
    result = db.table("watchlists").delete().eq("id", watchlist_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist nao encontrada")
    return ok_response("Watchlist excluida com sucesso")


@router.post("/{watchlist_id}/itens")
async def adicionar_item(watchlist_id: str, body: WatchlistItemCreate, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    # Verify watchlist belongs to org
    wl = db.table("watchlists").select("id").eq("id", watchlist_id).eq("org_id", org_id).execute()
    if not wl.data:
        raise HTTPException(status_code=404, detail="Watchlist nao encontrada")

    data = body.model_dump(exclude_none=True)
    data["watchlist_id"] = watchlist_id
    result = db.table("watchlist_itens").insert(data).execute()
    row = first_or_none(result)
    return success_response(row)


@router.delete("/itens/{item_id}")
async def remover_item(item_id: str, authorization: Optional[str] = Header(None)):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)

    # Verify the item belongs to a watchlist owned by the org
    item = db.table("watchlist_itens").select("watchlist_id").eq("id", item_id).execute()
    if not item.data:
        raise HTTPException(status_code=404, detail="Item nao encontrado")
    wl = db.table("watchlists").select("id").eq("id", item.data[0]["watchlist_id"]).eq("org_id", org_id).execute()
    if not wl.data:
        raise HTTPException(status_code=403, detail="Acesso negado")

    db.table("watchlist_itens").delete().eq("id", item_id).execute()
    return ok_response("Item removido com sucesso")
