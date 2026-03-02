"""Categories service — hierarchy management."""
import logging
from typing import Dict, List, Optional
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class CategoriasService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self, tipo: Optional[str] = None) -> List[Dict]:
        query = self.db.table("categorias").select("*").order("ordem")
        if tipo:
            query = query.eq("tipo", tipo)
        result = query.execute()
        return result.data or []

    async def obter(self, categoria_id: str) -> Optional[Dict]:
        result = self.db.table("categorias").select("*").eq("id", categoria_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        data["is_sistema"] = False
        result = self.db.table("categorias").insert(data).execute()
        row = first_or_none(result)
        return row

    async def atualizar(self, categoria_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("categorias").update(data).eq("id", categoria_id).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, categoria_id: str) -> bool:
        self.db.table("categorias").delete().eq("id", categoria_id).execute()
        return True

    async def arvore(self, tipo: Optional[str] = None) -> List[Dict]:
        """Return categories organized as a tree (parent/children)."""
        todas = await self.listar(tipo)
        raiz = []
        por_id = {c["id"]: {**c, "subcategorias": []} for c in todas}

        for c in todas:
            pai_id = c.get("categoria_pai_id")
            if pai_id and pai_id in por_id:
                por_id[pai_id]["subcategorias"].append(por_id[c["id"]])
            else:
                raiz.append(por_id[c["id"]])

        return raiz
