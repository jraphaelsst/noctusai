"""Holdings service — stock/asset management with average price calculation."""
import logging
from typing import Dict, List, Optional
from fastapi import HTTPException
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class AtivosService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self, carteira_id: Optional[str] = None) -> List[Dict]:
        query = self.db.table("ativos").select("*").eq("org_id", self.org_id).order("valor_atual", desc=True)
        if carteira_id:
            query = query.eq("carteira_id", carteira_id)
        result = query.execute()
        return result.data or []

    async def obter(self, ativo_id: str) -> Optional[Dict]:
        result = self.db.table("ativos").select("*").eq("id", ativo_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("ativos").insert(data).execute()
        row = first_or_none(result)
        return row

    async def atualizar(self, ativo_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("ativos").update(data).eq("id", ativo_id).eq("org_id", self.org_id).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, ativo_id: str) -> bool:
        check = self.db.table("ativos").select("id").eq("id", ativo_id).eq("org_id", self.org_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Ativo não encontrado")
        self.db.table("ativos").delete().eq("id", ativo_id).eq("org_id", self.org_id).execute()
        return True

    async def excluir_operacao(self, operacao_id: str) -> bool:
        """Delete an operation and recalculate the associated holding."""
        op_result = self.db.table("operacoes").select("*").eq("id", operacao_id).eq("org_id", self.org_id).execute()
        if not op_result.data:
            raise HTTPException(status_code=404, detail="Operação não encontrada")
        op = op_result.data[0]

        self.db.table("operacoes").delete().eq("id", operacao_id).eq("org_id", self.org_id).execute()

        # Recalculate holding from remaining operations
        if op.get("ativo_id"):
            await self._recalcular_ativo_completo(op["ativo_id"])

        return True

    async def registrar_operacao(self, data: Dict) -> Dict:
        """Register buy/sell operation and recalculate holding."""
        result = self.db.table("operacoes").insert(data).execute()
        row = first_or_none(result)

        if row and data.get("ativo_id"):
            await self._recalcular_ativo(data["ativo_id"], data["tipo"], data)
        elif row and not data.get("ativo_id"):
            # Auto-create holding if needed
            ativo = await self._encontrar_ou_criar_ativo(data)
            if ativo:
                self.db.table("operacoes").update({"ativo_id": ativo["id"]}).eq("id", row["id"]).execute()
                await self._recalcular_ativo(ativo["id"], data["tipo"], data)

        return row

    async def _encontrar_ou_criar_ativo(self, operacao: Dict) -> Optional[Dict]:
        """Find existing holding by ticker or create new one."""
        existing = self.db.table("ativos").select("*").eq("carteira_id", operacao["carteira_id"]).eq("ticker", operacao["ticker"]).execute()
        if existing.data:
            return existing.data[0]

        # Create new holding
        novo = {
            "carteira_id": operacao["carteira_id"],
            "org_id": self.org_id,
            "ticker": operacao["ticker"],
            "tipo": "acao",
            "quantidade": 0,
            "preco_medio": 0,
        }
        result = self.db.table("ativos").insert(novo).execute()
        return first_or_none(result)

    async def _recalcular_ativo_completo(self, ativo_id: str):
        """Recalculate holding from ALL operations using FIFO lot tracking."""
        ops = (
            self.db.table("operacoes")
            .select("*")
            .eq("ativo_id", ativo_id)
            .order("data")
            .order("created_at")
            .execute()
        )
        operacoes = ops.data or []

        # FIFO lot queue: each entry is {"quantidade": float, "preco": float}
        lots: list[dict] = []

        for op in operacoes:
            tipo = op.get("tipo", "")
            qtd_op = float(op.get("quantidade") or 0)
            preco_op = float(op.get("preco_unitario") or 0)

            if tipo == "compra":
                lots.append({"quantidade": qtd_op, "preco": preco_op})

            elif tipo == "venda":
                remaining = qtd_op
                while remaining > 0 and lots:
                    oldest = lots[0]
                    if oldest["quantidade"] <= remaining:
                        remaining -= oldest["quantidade"]
                        lots.pop(0)
                    else:
                        oldest["quantidade"] -= remaining
                        remaining = 0

            elif tipo == "split":
                if qtd_op > 0:
                    for lot in lots:
                        lot["quantidade"] *= qtd_op
                        lot["preco"] /= qtd_op

            # dividendo, jcp, rendimento, bonificacao — no impact on cost basis

        qtd = sum(lot["quantidade"] for lot in lots)
        custo_total = sum(lot["quantidade"] * lot["preco"] for lot in lots)
        pm = custo_total / qtd if qtd > 0 else 0

        update = {"quantidade": qtd, "preco_medio": round(pm, 4)}

        # Recalculate gain/loss
        ativo = await self.obter(ativo_id)
        if ativo:
            preco_atual = float(ativo.get("preco_atual", 0))
            if preco_atual > 0 and qtd > 0:
                update["valor_atual"] = round(preco_atual * qtd, 2)
                update["ganho_perda"] = round((preco_atual - pm) * qtd, 2)
                update["ganho_perda_pct"] = round(((preco_atual / pm) - 1) * 100, 4) if pm > 0 else 0

        try:
            self.db.table("ativos").update(update).eq("id", ativo_id).execute()
        except Exception as e:
            logger.error(f"Failed to recalculate holding {ativo_id}: {e}")

    async def _recalcular_ativo(self, ativo_id: str, tipo_op: str, operacao: Dict):
        """Recalculate holding using full FIFO lot replay."""
        await self._recalcular_ativo_completo(ativo_id)
