"""Budgets service — budget management with method support."""
import logging
from typing import Dict, List, Optional
from fastapi import HTTPException
from app.dependencies import first_or_none
from noctusai_lib.domain.metas import Target, compute_progress

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
        result = self.db.table("orcamentos").insert(data).execute()
        row = first_or_none(result)

        if row and itens:
            for item in itens:
                item["orcamento_id"] = row["id"]
            self.db.table("orcamento_itens").insert(itens).execute()

        return row

    async def atualizar(self, orcamento_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("orcamentos").update(data).eq("id", orcamento_id).eq("org_id", self.org_id).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, orcamento_id: str) -> bool:
        check = self.db.table("orcamentos").select("id").eq("id", orcamento_id).eq("org_id", self.org_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Orçamento não encontrado")
        self.db.table("orcamentos").delete().eq("id", orcamento_id).eq("org_id", self.org_id).execute()
        return True

    async def sincronizar_gastos(self, categoria_id: str, periodo_mes: str) -> int:
        """Sync valor_gasto from actual transactions for a category+month pair.

        Returns the number of budget items updated.
        """
        data_inicio = f"{periodo_mes}-01"
        ano, m = periodo_mes.split("-")
        m_int = int(m)
        if m_int == 12:
            data_fim = f"{int(ano)+1}-01-01"
        else:
            data_fim = f"{ano}-{m_int+1:02d}-01"

        # Sum despesas for this category in this month
        transacoes = self.db.table("transacoes").select("valor, tipo").eq(
            "org_id", self.org_id
        ).eq("categoria_id", categoria_id).eq("tipo", "despesa").gte(
            "data", data_inicio
        ).lt("data", data_fim).execute()

        total_gasto = sum(float(t.get("valor", 0)) for t in (transacoes.data or []))

        # Update matching budget items
        itens = self.db.table("orcamento_itens").select("id, orcamento_id").eq(
            "categoria_id", categoria_id
        ).eq("periodo_mes", periodo_mes).execute()

        updated = 0
        for item in (itens.data or []):
            # Verify the budget belongs to this org
            orc = self.db.table("orcamentos").select("id").eq(
                "id", item["orcamento_id"]
            ).eq("org_id", self.org_id).execute()
            if not (orc.data or []):
                continue
            self.db.table("orcamento_itens").update(
                {"valor_gasto": round(total_gasto, 2)}
            ).eq("id", item["id"]).execute()
            updated += 1

        return updated

    async def obter_progresso(self, orcamento_id: str, periodo_mes: str) -> Dict:
        """Get budget progress for a given month (syncs from transactions first)."""
        # Sync gastos for each category in this budget's items before returning
        itens_pre = self.db.table("orcamento_itens").select("categoria_id").eq(
            "orcamento_id", orcamento_id
        ).eq("periodo_mes", periodo_mes).execute()
        synced_cats = set()
        for item in (itens_pre.data or []):
            cat_id = item.get("categoria_id")
            if cat_id and cat_id not in synced_cats:
                try:
                    await self.sincronizar_gastos(cat_id, periodo_mes)
                except Exception as e:
                    logger.warning(f"Budget sync failed for category {cat_id}: {e}")
                synced_cats.add(cat_id)

        # Re-fetch with updated values
        itens_result = self.db.table("orcamento_itens").select("*, categoria:categorias(id,nome,icone,cor)").eq("orcamento_id", orcamento_id).eq("periodo_mes", periodo_mes).execute()
        itens = itens_result.data or []

        total_planejado = sum(float(i.get("valor_planejado", 0)) for i in itens)
        total_gasto = sum(float(i.get("valor_gasto", 0)) for i in itens)

        # Budget percent-used = current spending vs planned target. Same math as
        # goal accumulation; inverse semantic (spending vs accumulation).
        progress = compute_progress(
            target=Target(total_planejado),
            current=total_gasto,
        )

        return {
            "orcamento_id": orcamento_id,
            "periodo_mes": periodo_mes,
            "total_planejado": total_planejado,
            "total_gasto": total_gasto,
            "saldo": total_planejado - total_gasto,
            "percentual_usado": progress.percent_complete,
            "itens": itens,
        }

    async def listar_itens(self, orcamento_id: str, periodo_mes: Optional[str] = None) -> List[Dict]:
        query = self.db.table("orcamento_itens").select("*, categoria:categorias(id,nome,icone,cor)").eq("orcamento_id", orcamento_id)
        if periodo_mes:
            query = query.eq("periodo_mes", periodo_mes)
        result = query.execute()
        return result.data or []

    async def criar_item(self, data: Dict) -> Dict:
        result = self.db.table("orcamento_itens").insert(data).execute()
        row = first_or_none(result)
        return row

    async def atualizar_item(self, item_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("orcamento_itens").update(data).eq("id", item_id).execute()
        row = first_or_none(result)
        return row

    async def excluir_item(self, item_id: str) -> bool:
        self.db.table("orcamento_itens").delete().eq("id", item_id).execute()
        return True
