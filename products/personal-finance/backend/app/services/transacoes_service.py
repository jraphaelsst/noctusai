"""Transactions service — CRUD, filtering, categorization."""
import logging
from typing import Dict, List, Optional
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class TransacoesService:
    SEARCH_FIELDS = ["descricao", "comerciante", "notas"]

    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(
        self,
        conta_id: Optional[str] = None,
        categoria_id: Optional[str] = None,
        tipo: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        busca: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[Dict], int]:
        count_query = self.db.table("transacoes").select("id", count="exact").eq("org_id", self.org_id)
        query = self.db.table("transacoes").select("*, conta:contas!transacoes_conta_id_fkey(id,nome,cor,icone), categoria:categorias(id,nome,icone,cor)").eq("org_id", self.org_id).order("data", desc=True)

        if conta_id:
            count_query = count_query.eq("conta_id", conta_id)
            query = query.eq("conta_id", conta_id)
        if categoria_id:
            count_query = count_query.eq("categoria_id", categoria_id)
            query = query.eq("categoria_id", categoria_id)
        if tipo:
            count_query = count_query.eq("tipo", tipo)
            query = query.eq("tipo", tipo)
        if data_inicio:
            count_query = count_query.gte("data", data_inicio)
            query = query.gte("data", data_inicio)
        if data_fim:
            count_query = count_query.lte("data", data_fim)
            query = query.lte("data", data_fim)

        # Apply search filter server-side before pagination
        if busca:
            search_filter = ",".join(f"{f}.ilike.%{busca}%" for f in self.SEARCH_FIELDS)
            count_query = count_query.or_(search_filter)
            query = query.or_(search_filter)

        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        data = result.data or []

        count_result = count_query.execute()
        total = count_result.count if count_result.count is not None else len(data)

        return data, total

    async def obter(self, transacao_id: str) -> Optional[Dict]:
        result = self.db.table("transacoes").select("*, conta:contas!transacoes_conta_id_fkey(id,nome), categoria:categorias(id,nome,icone)").eq("id", transacao_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id

        # Validate transfer has destination account
        if data.get("tipo") == "transferencia" and not data.get("conta_destino_id"):
            raise ValueError("conta_destino_id obrigatorio para transferencias")

        result = self.db.table("transacoes").insert(data).execute()
        row = first_or_none(result)

        # Update account balance
        if row:
            await self._atualizar_saldo_conta(data["conta_id"], float(data["valor"]), data["tipo"])
            if data.get("conta_destino_id") and data["tipo"] == "transferencia":
                await self._atualizar_saldo_conta(data["conta_destino_id"], float(data["valor"]), "receita")
            await self._sincronizar_orcamento(data.get("categoria_id"), data.get("data"))
            await self._invalidar_cache_mensal(data.get("data"))

        return row

    async def atualizar(self, transacao_id: str, data: Dict) -> Optional[Dict]:
        # Fetch old transaction to reverse balance
        old = self.db.table("transacoes").select("*").eq("id", transacao_id).eq("org_id", self.org_id).single().execute()
        if not old.data:
            return None

        result = self.db.table("transacoes").update(data).eq("id", transacao_id).eq("org_id", self.org_id).execute()
        row = first_or_none(result)
        if not row:
            return None

        old_t = old.data
        new_t = row

        # Reverse old balance effect
        reverse_tipo = "receita" if old_t["tipo"] == "despesa" else "despesa"
        if old_t["tipo"] == "transferencia":
            reverse_tipo = "receita"  # reverse source debit
        await self._atualizar_saldo_conta(old_t["conta_id"], float(old_t["valor"]), reverse_tipo)
        if old_t.get("conta_destino_id") and old_t["tipo"] == "transferencia":
            await self._atualizar_saldo_conta(old_t["conta_destino_id"], float(old_t["valor"]), "despesa")

        # Apply new balance effect
        await self._atualizar_saldo_conta(new_t["conta_id"], float(new_t["valor"]), new_t["tipo"])
        if new_t.get("conta_destino_id") and new_t["tipo"] == "transferencia":
            await self._atualizar_saldo_conta(new_t["conta_destino_id"], float(new_t["valor"]), "receita")

        # Sync budget + cache for both old and new category/month
        await self._sincronizar_orcamento(old_t.get("categoria_id"), old_t.get("data"))
        await self._sincronizar_orcamento(new_t.get("categoria_id"), new_t.get("data"))
        await self._invalidar_cache_mensal(old_t.get("data"))
        await self._invalidar_cache_mensal(new_t.get("data"))

        return row

    async def excluir(self, transacao_id: str) -> bool:
        # Fetch transaction to reverse balance
        transacao = self.db.table("transacoes").select("*").eq("id", transacao_id).eq("org_id", self.org_id).single().execute()
        if transacao.data:
            t = transacao.data
            reverse_tipo = "receita" if t["tipo"] == "despesa" else "despesa"
            if t["tipo"] == "transferencia":
                reverse_tipo = "receita"
            await self._atualizar_saldo_conta(t["conta_id"], float(t["valor"]), reverse_tipo)
            if t.get("conta_destino_id") and t["tipo"] == "transferencia":
                await self._atualizar_saldo_conta(t["conta_destino_id"], float(t["valor"]), "despesa")

        self.db.table("transacoes").delete().eq("id", transacao_id).eq("org_id", self.org_id).execute()

        if transacao.data:
            t = transacao.data
            await self._sincronizar_orcamento(t.get("categoria_id"), t.get("data"))
            await self._invalidar_cache_mensal(t.get("data"))

        return True

    async def por_categoria(self, data_inicio: str, data_fim: str) -> List[Dict]:
        result = self.db.table("transacoes").select("categoria_id, valor, tipo, categoria:categorias(id,nome,icone,cor)").eq("org_id", self.org_id).gte("data", data_inicio).lte("data", data_fim).eq("tipo", "despesa").execute()
        data = result.data or []

        categorias = {}
        for t in data:
            cat_id = t.get("categoria_id") or "sem_categoria"
            if cat_id not in categorias:
                cat_info = t.get("categoria") or {}
                categorias[cat_id] = {
                    "categoria_id": cat_id,
                    "nome": cat_info.get("nome", "Sem categoria"),
                    "icone": cat_info.get("icone", ""),
                    "cor": cat_info.get("cor", "#6b7280"),
                    "total": 0,
                    "count": 0,
                }
            categorias[cat_id]["total"] += float(t.get("valor", 0))
            categorias[cat_id]["count"] += 1

        return sorted(categorias.values(), key=lambda x: x["total"], reverse=True)

    async def _atualizar_saldo_conta(self, conta_id: str, valor: float, tipo: str):
        try:
            conta = self.db.table("contas").select("saldo").eq("id", conta_id).single().execute()
            if conta.data:
                saldo_atual = float(conta.data.get("saldo", 0))
                if tipo == "receita":
                    novo_saldo = saldo_atual + valor
                elif tipo == "despesa":
                    novo_saldo = saldo_atual - valor
                else:
                    novo_saldo = saldo_atual - valor  # transfer from source
                self.db.table("contas").update({"saldo": novo_saldo}).eq("id", conta_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update account balance: {e}")

    async def _sincronizar_orcamento(self, categoria_id: Optional[str], data_transacao: Optional[str]):
        """Sync budget items for the transaction's category+month."""
        if not categoria_id or not data_transacao:
            return
        try:
            periodo_mes = data_transacao[:7]  # YYYY-MM
            from app.services.orcamentos_service import OrcamentosService
            orc_service = OrcamentosService(self.db, self.org_id)
            await orc_service.sincronizar_gastos(categoria_id, periodo_mes)
        except Exception as e:
            logger.warning(f"Budget sync failed: {e}")

    async def _invalidar_cache_mensal(self, data_transacao: Optional[str]):
        """Recompute and cache the monthly summary for the transaction's month."""
        if not data_transacao:
            return
        try:
            periodo_mes = data_transacao[:7]  # YYYY-MM
            from app.services.relatorios_service import RelatoriosService
            rel_service = RelatoriosService(self.db, self.org_id)
            await rel_service.atualizar_resumo_mensal(periodo_mes)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
