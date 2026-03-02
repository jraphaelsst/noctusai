"""Net worth service — patrimony tracking and snapshots."""
import logging
from typing import Dict, List, Optional
from datetime import date

logger = logging.getLogger(__name__)


class PatrimonioService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def calcular_atual(self) -> Dict:
        """Calculate current net worth from all accounts and investments."""
        # Get all active accounts
        contas = self.db.table("contas").select("id,nome,tipo,saldo,ativo").eq("org_id", self.org_id).eq("ativo", True).execute()
        contas_data = contas.data or []

        total_ativos = 0
        total_passivos = 0
        detalhamento = {"contas": [], "investimentos": []}

        for conta in contas_data:
            saldo = float(conta.get("saldo", 0))
            tipo = conta.get("tipo", "outro")

            if tipo in ("emprestimo", "cartao_credito") and saldo < 0:
                total_passivos += abs(saldo)
            else:
                total_ativos += max(saldo, 0)
                if saldo < 0:
                    total_passivos += abs(saldo)

            detalhamento["contas"].append({
                "id": conta["id"],
                "nome": conta["nome"],
                "tipo": tipo,
                "saldo": saldo,
            })

        # Get investment portfolios
        ativos = self.db.table("ativos").select("id,ticker,valor_atual,carteira_id").eq("org_id", self.org_id).execute()
        for ativo in (ativos.data or []):
            valor = float(ativo.get("valor_atual", 0))
            total_ativos += valor
            detalhamento["investimentos"].append({
                "ticker": ativo.get("ticker"),
                "valor": valor,
            })

        patrimonio_liquido = total_ativos - total_passivos

        return {
            "total_ativos": round(total_ativos, 2),
            "total_passivos": round(total_passivos, 2),
            "patrimonio_liquido": round(patrimonio_liquido, 2),
            "detalhamento": detalhamento,
        }

    async def criar_snapshot(self, data_snapshot: Optional[str] = None) -> Dict:
        """Create or update a net worth snapshot for the given date."""
        atual = await self.calcular_atual()
        snapshot_date = data_snapshot or date.today().isoformat()
        snapshot = {
            "org_id": self.org_id,
            "data": snapshot_date,
            "total_ativos": atual["total_ativos"],
            "total_passivos": atual["total_passivos"],
            "patrimonio_liquido": atual["patrimonio_liquido"],
            "detalhamento": atual["detalhamento"],
        }

        # Check for existing snapshot on this date to avoid duplicates
        existing = self.db.table("patrimonio_snapshots").select("id").eq("org_id", self.org_id).eq("data", snapshot_date).execute()
        if existing.data:
            result = self.db.table("patrimonio_snapshots").update(snapshot).eq("id", existing.data[0]["id"]).select().single().execute()
        else:
            result = self.db.table("patrimonio_snapshots").insert(snapshot).select().single().execute()
        return result.data

    async def historico(self, limite: int = 24) -> List[Dict]:
        """Get net worth history (most recent snapshots)."""
        result = self.db.table("patrimonio_snapshots").select("*").eq("org_id", self.org_id).order("data", desc=True).limit(limite).execute()
        data = result.data or []
        data.reverse()  # Chronological order
        return data
