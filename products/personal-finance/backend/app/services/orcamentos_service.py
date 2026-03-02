"""Budgets service — budget management with method support."""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OrcamentosService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self) -> List[Dict]:
        result = self.db.table("orcamentos").select("*").eq("org_id", self.org_id).order("created_at", desc=True).execute()
        return result.data or []

    async def obter(self, orcamento_id: str) -> Optional[Dict]:
        result = self.db.table("orcamentos").select("*").eq("id", orcamento_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict, itens: Optional[List[Dict]] = None) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("orcamentos").insert(data).select().single().execute()

        if result.data and itens:
            for item in itens:
                item["orcamento_id"] = result.data["id"]
            self.db.table("orcamento_itens").insert(itens).execute()

        return result.data

    async def atualizar(self, orcamento_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("orcamentos").update(data).eq("id", orcamento_id).eq("org_id", self.org_id).select().single().execute()
        return result.data

    async def excluir(self, orcamento_id: str) -> bool:
        self.db.table("orcamentos").delete().eq("id", orcamento_id).eq("org_id", self.org_id).execute()
        return True

    async def obter_progresso(self, orcamento_id: str, periodo_mes: str) -> Dict:
        """Get budget progress for a given month."""
        itens_result = self.db.table("orcamento_itens").select("*, categoria:categorias(id,nome,icone,cor)").eq("orcamento_id", orcamento_id).eq("periodo_mes", periodo_mes).execute()
        itens = itens_result.data or []

        total_planejado = sum(float(i.get("valor_planejado", 0)) for i in itens)
        total_gasto = sum(float(i.get("valor_gasto", 0)) for i in itens)

        return {
            "orcamento_id": orcamento_id,
            "periodo_mes": periodo_mes,
            "total_planejado": total_planejado,
            "total_gasto": total_gasto,
            "saldo": total_planejado - total_gasto,
            "percentual_usado": (total_gasto / total_planejado * 100) if total_planejado > 0 else 0,
            "itens": itens,
        }

    async def listar_itens(self, orcamento_id: str, periodo_mes: Optional[str] = None) -> List[Dict]:
        query = self.db.table("orcamento_itens").select("*, categoria:categorias(id,nome,icone,cor)").eq("orcamento_id", orcamento_id)
        if periodo_mes:
            query = query.eq("periodo_mes", periodo_mes)
        result = query.execute()
        return result.data or []

    async def criar_item(self, data: Dict) -> Dict:
        result = self.db.table("orcamento_itens").insert(data).select().single().execute()
        return result.data

    async def atualizar_item(self, item_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("orcamento_itens").update(data).eq("id", item_id).select().single().execute()
        return result.data

    async def excluir_item(self, item_id: str) -> bool:
        self.db.table("orcamento_itens").delete().eq("id", item_id).execute()
        return True
