"""Reports service — monthly/annual aggregation with resumos_mensais cache."""
import json
import logging
from typing import Dict, List, Optional
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class RelatoriosService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def relatorio_mensal(self, mes: str) -> Dict:
        """Generate monthly report for YYYY-MM. Uses cache if available."""
        cached = self._buscar_cache(mes)
        if cached:
            return cached

        report = await self._computar_relatorio_mensal(mes)
        self._salvar_cache(mes, report)
        return report

    async def relatorio_anual(self, ano: str) -> Dict:
        """Generate annual report. Batch-fetches cache, only computes uncached months."""
        # Batch-fetch all 12 months from cache in 1 query
        cache_result = self.db.table("resumos_mensais").select("mes, dados").eq(
            "org_id", self.org_id
        ).gte("mes", f"{ano}-01").lte("mes", f"{ano}-12").execute()

        cached_map = {}
        for row in (cache_result.data or []):
            dados = row.get("dados")
            if isinstance(dados, str):
                dados = json.loads(dados)
            cached_map[row["mes"]] = dados

        meses = []
        receita_anual = 0
        despesa_anual = 0

        for m in range(1, 13):
            mes_str = f"{ano}-{m:02d}"
            if mes_str in cached_map:
                relatorio = cached_map[mes_str]
            else:
                relatorio = await self._computar_relatorio_mensal(mes_str)
                self._salvar_cache(mes_str, relatorio)
            meses.append(relatorio)
            receita_anual += relatorio["receita_total"]
            despesa_anual += relatorio["despesa_total"]

        return {
            "ano": ano,
            "receita_anual": round(receita_anual, 2),
            "despesa_anual": round(despesa_anual, 2),
            "fluxo_liquido_anual": round(receita_anual - despesa_anual, 2),
            "taxa_poupanca_anual": round(((receita_anual - despesa_anual) / receita_anual * 100) if receita_anual > 0 else 0, 2),
            "meses": meses,
        }

    async def fluxo_caixa(self, data_inicio: str, data_fim: str) -> Dict:
        """Cash flow report for a date range."""
        transacoes = self.db.table("transacoes").select("data, valor, tipo").eq("org_id", self.org_id).gte("data", data_inicio).lte("data", data_fim).order("data").execute()
        data = transacoes.data or []

        fluxo_diario = {}
        for t in data:
            dia = t.get("data")
            if dia not in fluxo_diario:
                fluxo_diario[dia] = {"data": dia, "receitas": 0, "despesas": 0, "liquido": 0}

            valor = float(t.get("valor", 0))
            if t.get("tipo") == "receita":
                fluxo_diario[dia]["receitas"] += valor
            elif t.get("tipo") == "despesa":
                fluxo_diario[dia]["despesas"] += valor

        for dia in fluxo_diario.values():
            dia["liquido"] = round(dia["receitas"] - dia["despesas"], 2)
            dia["receitas"] = round(dia["receitas"], 2)
            dia["despesas"] = round(dia["despesas"], 2)

        return {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "fluxo": sorted(fluxo_diario.values(), key=lambda x: x["data"]),
        }

    async def atualizar_resumo_mensal(self, mes: str):
        """Recompute and cache the monthly summary. Called by TransacoesService on changes."""
        report = await self._computar_relatorio_mensal(mes)
        self._salvar_cache(mes, report)
        return report

    async def _computar_relatorio_mensal(self, mes: str) -> Dict:
        """Pure computation of monthly report — no cache interaction."""
        data_inicio = f"{mes}-01"
        ano, m = mes.split("-")
        m_int = int(m)
        if m_int == 12:
            data_fim = f"{int(ano)+1}-01-01"
        else:
            data_fim = f"{ano}-{m_int+1:02d}-01"

        transacoes = self.db.table("transacoes").select("*, categoria:categorias(id,nome,icone,cor)").eq("org_id", self.org_id).gte("data", data_inicio).lt("data", data_fim).execute()
        data = transacoes.data or []

        receita_total = sum(float(t.get("valor", 0)) for t in data if t.get("tipo") == "receita")
        despesa_total = sum(float(t.get("valor", 0)) for t in data if t.get("tipo") == "despesa")
        fluxo_liquido = receita_total - despesa_total
        taxa_poupanca = (fluxo_liquido / receita_total * 100) if receita_total > 0 else 0

        # Top categories by spending
        categorias = {}
        for t in data:
            if t.get("tipo") != "despesa":
                continue
            cat = t.get("categoria") or {}
            cat_nome = cat.get("nome", "Sem categoria")
            if cat_nome not in categorias:
                categorias[cat_nome] = {"nome": cat_nome, "icone": cat.get("icone", ""), "cor": cat.get("cor", ""), "total": 0}
            categorias[cat_nome]["total"] += float(t.get("valor", 0))

        top_categorias = sorted(categorias.values(), key=lambda x: x["total"], reverse=True)[:10]

        return {
            "mes": mes,
            "receita_total": round(receita_total, 2),
            "despesa_total": round(despesa_total, 2),
            "fluxo_liquido": round(fluxo_liquido, 2),
            "taxa_poupanca": round(taxa_poupanca, 2),
            "total_transacoes": len(data),
            "top_categorias": top_categorias,
        }

    def _buscar_cache(self, mes: str) -> Optional[Dict]:
        """Look up cached monthly summary. Returns None on miss or error."""
        try:
            result = self.db.table("resumos_mensais").select("dados").eq(
                "org_id", self.org_id
            ).eq("mes", mes).execute()
            if result.data:
                dados = result.data[0].get("dados")
                if isinstance(dados, str):
                    dados = json.loads(dados)
                return dados
        except Exception as e:
            logger.warning(f"Cache lookup failed for {mes}: {e}")
        return None

    def _salvar_cache(self, mes: str, report: Dict):
        """Upsert monthly summary into resumos_mensais."""
        try:
            existing = self.db.table("resumos_mensais").select("id").eq(
                "org_id", self.org_id
            ).eq("mes", mes).execute()

            payload = {
                "org_id": self.org_id,
                "mes": mes,
                "dados": report,
            }

            if existing.data:
                self.db.table("resumos_mensais").update(payload).eq(
                    "id", existing.data[0]["id"]
                ).execute()
            else:
                self.db.table("resumos_mensais").insert(payload).execute()
        except Exception as e:
            logger.warning(f"Cache save failed for {mes}: {e}")
