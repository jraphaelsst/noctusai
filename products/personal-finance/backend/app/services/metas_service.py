"""Financial goals service — goal tracking and contributions."""
import logging
from typing import Dict, List, Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)


class MetasService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def listar(self, status: Optional[str] = None) -> List[Dict]:
        query = self.db.table("metas").select("*").eq("org_id", self.org_id).order("prioridade").order("created_at", desc=True)
        if status:
            query = query.eq("status", status)
        result = query.execute()
        data = result.data or []

        # Enrich with progress info
        for meta in data:
            valor_alvo = float(meta.get("valor_alvo", 1))
            valor_atual = float(meta.get("valor_atual", 0))
            meta["percentual"] = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)

        return data

    async def obter(self, meta_id: str) -> Optional[Dict]:
        result = self.db.table("metas").select("*").eq("id", meta_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("metas").insert(data).select().single().execute()
        return result.data

    async def atualizar(self, meta_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("metas").update(data).eq("id", meta_id).eq("org_id", self.org_id).select().single().execute()
        return result.data

    async def excluir(self, meta_id: str) -> bool:
        self.db.table("metas").delete().eq("id", meta_id).eq("org_id", self.org_id).execute()
        return True

    async def adicionar_contribuicao(self, meta_id: str, data: Dict) -> Dict:
        data["meta_id"] = meta_id
        result = self.db.table("meta_contribuicoes").insert(data).select().single().execute()

        # Update meta valor_atual
        if result.data:
            meta = await self.obter(meta_id)
            if meta:
                novo_valor = float(meta.get("valor_atual", 0)) + float(data.get("valor", 0))
                update_data = {"valor_atual": novo_valor}
                if novo_valor >= float(meta.get("valor_alvo", 0)):
                    update_data["status"] = "concluida"
                self.db.table("metas").update(update_data).eq("id", meta_id).execute()

        return result.data

    async def obter_progresso(self, meta_id: str) -> Dict:
        meta = await self.obter(meta_id)
        if not meta:
            return {}

        contribuicoes = self.db.table("meta_contribuicoes").select("*").eq("meta_id", meta_id).order("data", desc=True).execute()

        valor_alvo = float(meta.get("valor_alvo", 1))
        valor_atual = float(meta.get("valor_atual", 0))
        percentual = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)

        # Estimate completion date
        data_previsao = None
        contribs = contribuicoes.data or []
        if contribs and valor_atual < valor_alvo:
            total_contrib = sum(float(c.get("valor", 0)) for c in contribs)
            meses_com_contrib = len(set(c.get("data", "")[:7] for c in contribs))
            if meses_com_contrib > 0:
                media_mensal = total_contrib / meses_com_contrib
                if media_mensal > 0:
                    meses_restantes = (valor_alvo - valor_atual) / media_mensal
                    from dateutil.relativedelta import relativedelta
                    data_previsao = (date.today() + relativedelta(months=int(meses_restantes))).isoformat()

        return {
            "meta": meta,
            "percentual": percentual,
            "faltam": max(valor_alvo - valor_atual, 0),
            "data_previsao": data_previsao,
            "contribuicoes": contribs,
        }
