"""Watchlist service — stock watchlist management."""
import logging
from typing import Dict, List, Optional
from fastapi import HTTPException
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class WatchlistService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self) -> List[Dict]:
        result = self.db.table("watchlists").select("*").eq("org_id", self.org_id).order("created_at").execute()
        return result.data or []

    async def obter(self, watchlist_id: str) -> Dict:
        result = self.db.table("watchlists").select("*").eq("id", watchlist_id).eq("org_id", self.org_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Watchlist não encontrada")

        itens = self.db.table("watchlist_itens").select("*").eq("watchlist_id", watchlist_id).order("created_at").execute()
        result.data["itens"] = itens.data or []
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("watchlists").insert(data).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, watchlist_id: str) -> bool:
        check = self.db.table("watchlists").select("id").eq("id", watchlist_id).eq("org_id", self.org_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Watchlist não encontrada")
        self.db.table("watchlists").delete().eq("id", watchlist_id).eq("org_id", self.org_id).execute()
        return True

    async def adicionar_item(self, watchlist_id: str, data: Dict) -> Dict:
        # Verify watchlist belongs to org
        wl = self.db.table("watchlists").select("id").eq("id", watchlist_id).eq("org_id", self.org_id).execute()
        if not wl.data:
            raise HTTPException(status_code=404, detail="Watchlist não encontrada")

        data["watchlist_id"] = watchlist_id
        result = self.db.table("watchlist_itens").insert(data).execute()
        row = first_or_none(result)
        return row

    async def remover_item(self, item_id: str) -> bool:
        # Verify the item belongs to a watchlist owned by the org
        item = self.db.table("watchlist_itens").select("watchlist_id").eq("id", item_id).execute()
        if not item.data:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        wl = self.db.table("watchlists").select("id").eq("id", item.data[0]["watchlist_id"]).eq("org_id", self.org_id).execute()
        if not wl.data:
            raise HTTPException(status_code=403, detail="Acesso negado")

        self.db.table("watchlist_itens").delete().eq("id", item_id).execute()
        return True
