"""Portfolio service — portfolio management and summary."""
import logging
from typing import Dict, List, Optional
from fastapi import HTTPException
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class CarteiraService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self) -> List[Dict]:
        result = self.db.table("carteiras").select("*").eq("org_id", self.org_id).order("created_at").execute()
        carteiras = result.data or []

        if not carteiras:
            return carteiras

        # Fetch ALL ativos for all carteiras in a single query (avoid N+1)
        carteira_ids = [c["id"] for c in carteiras]
        ativos_result = self.db.table("ativos").select("carteira_id,valor_atual,ganho_perda,tipo").in_("carteira_id", carteira_ids).execute()
        all_ativos = ativos_result.data or []

        # Group ativos by carteira_id
        ativos_por_carteira: Dict[str, List[Dict]] = {}
        for ativo in all_ativos:
            cid = ativo.get("carteira_id")
            if cid:
                ativos_por_carteira.setdefault(cid, []).append(ativo)

        # Enrich each carteira with summary from grouped data
        for carteira in carteiras:
            holdings = ativos_por_carteira.get(carteira["id"], [])
            carteira["valor_total"] = sum(float(a.get("valor_atual", 0)) for a in holdings)
            carteira["ganho_perda_total"] = sum(float(a.get("ganho_perda", 0)) for a in holdings)
            carteira["total_ativos"] = len(holdings)

        return carteiras

    async def obter(self, carteira_id: str) -> Optional[Dict]:
        result = self.db.table("carteiras").select("*").eq("id", carteira_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("carteiras").insert(data).execute()
        row = first_or_none(result)
        return row

    async def atualizar(self, carteira_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("carteiras").update(data).eq("id", carteira_id).eq("org_id", self.org_id).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, carteira_id: str) -> bool:
        check = self.db.table("carteiras").select("id").eq("id", carteira_id).eq("org_id", self.org_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Carteira não encontrada")
        self.db.table("carteiras").delete().eq("id", carteira_id).eq("org_id", self.org_id).execute()
        return True

    async def resumo(self, carteira_id: str) -> Dict:
        """Get portfolio summary with allocation breakdown."""
        carteira = await self.obter(carteira_id)
        if not carteira:
            return {}

        ativos_result = self.db.table("ativos").select("*").eq("carteira_id", carteira_id).order("valor_atual", desc=True).execute()
        ativos = ativos_result.data or []

        valor_total = sum(float(a.get("valor_atual", 0)) for a in ativos)
        custo_total = sum(float(a.get("preco_medio", 0)) * float(a.get("quantidade", 0)) for a in ativos)
        ganho_perda_total = sum(float(a.get("ganho_perda", 0)) for a in ativos)
        ganho_perda_pct = ((valor_total / custo_total - 1) * 100) if custo_total > 0 else 0

        # Allocation by type
        alocacao = {}
        for ativo in ativos:
            tipo = ativo.get("tipo", "outro")
            if tipo not in alocacao:
                alocacao[tipo] = {"tipo": tipo, "valor": 0, "percentual": 0}
            alocacao[tipo]["valor"] += float(ativo.get("valor_atual", 0))

        if valor_total > 0:
            for a in alocacao.values():
                a["percentual"] = round(a["valor"] / valor_total * 100, 2)

        # Target allocation
        alocacao_alvo = self.db.table("alocacao_alvo").select("*").eq("carteira_id", carteira_id).execute()

        return {
            "carteira": carteira,
            "valor_total": valor_total,
            "custo_total": custo_total,
            "ganho_perda_total": ganho_perda_total,
            "ganho_perda_pct": round(ganho_perda_pct, 2),
            "total_ativos": len(ativos),
            "ativos": ativos,
            "alocacao_atual": list(alocacao.values()),
            "alocacao_alvo": alocacao_alvo.data or [],
        }
