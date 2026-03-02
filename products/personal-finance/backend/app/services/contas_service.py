"""Accounts service — CRUD and balance operations."""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ContasService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self, ativo: Optional[bool] = None) -> List[Dict]:
        query = self.db.table("contas").select("*").eq("org_id", self.org_id).order("created_at")
        if ativo is not None:
            query = query.eq("ativo", ativo)
        result = query.execute()
        return result.data or []

    async def obter(self, conta_id: str) -> Optional[Dict]:
        result = self.db.table("contas").select("*").eq("id", conta_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("contas").insert(data).select().single().execute()
        return result.data

    async def atualizar(self, conta_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("contas").update(data).eq("id", conta_id).eq("org_id", self.org_id).select().single().execute()
        return result.data

    async def excluir(self, conta_id: str) -> bool:
        self.db.table("contas").delete().eq("id", conta_id).eq("org_id", self.org_id).execute()
        return True

    async def obter_saldos(self) -> List[Dict]:
        result = self.db.table("contas").select("id,nome,tipo,instituicao,saldo,moeda,cor,icone,ativo").eq("org_id", self.org_id).eq("ativo", True).order("nome").execute()
        return result.data or []
