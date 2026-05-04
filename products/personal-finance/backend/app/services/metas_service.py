"""Financial goals service — goal tracking and contributions."""
import logging
from typing import Dict, List, Optional
from datetime import date
from fastapi import HTTPException
from app.dependencies import first_or_none
from noctusai_lib.domain.metas import (
    Contribution,
    Target,
    accumulate_contribution,
    compute_progress,
)

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

        # Enrich with progress info via seed compute_progress
        for meta in data:
            valor_alvo = float(meta.get("valor_alvo", 0))
            valor_atual = float(meta.get("valor_atual", 0))
            progress = compute_progress(target=Target(valor_alvo), current=valor_atual)
            meta["percentual"] = progress.percent_complete

        return data

    async def obter(self, meta_id: str) -> Optional[Dict]:
        result = self.db.table("metas").select("*").eq("id", meta_id).eq("org_id", self.org_id).single().execute()
        return result.data

    async def criar(self, data: Dict) -> Dict:
        data["org_id"] = self.org_id
        result = self.db.table("metas").insert(data).execute()
        row = first_or_none(result)
        return row

    async def atualizar(self, meta_id: str, data: Dict) -> Optional[Dict]:
        result = self.db.table("metas").update(data).eq("id", meta_id).eq("org_id", self.org_id).execute()
        row = first_or_none(result)
        return row

    async def excluir(self, meta_id: str) -> bool:
        check = self.db.table("metas").select("id").eq("id", meta_id).eq("org_id", self.org_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Meta não encontrada")
        self.db.table("metas").delete().eq("id", meta_id).eq("org_id", self.org_id).execute()
        return True

    async def adicionar_contribuicao(self, meta_id: str, data: Dict) -> Dict:
        data["meta_id"] = meta_id
        result = self.db.table("meta_contribuicoes").insert(data).execute()
        row = first_or_none(result)

        # Update meta valor_atual via seed accumulate_contribution
        if row:
            meta = await self.obter(meta_id)
            if meta:
                transition = accumulate_contribution(
                    target=float(meta.get("valor_alvo", 0)),
                    current=float(meta.get("valor_atual", 0)),
                    increment=float(data.get("valor", 0)),
                )
                update_data = {"valor_atual": transition.new_current}
                if transition.completed:
                    update_data["status"] = "concluida"
                self.db.table("metas").update(update_data).eq("id", meta_id).execute()

        return row

    async def obter_progresso(self, meta_id: str) -> Dict:
        meta = await self.obter(meta_id)
        if not meta:
            return {}

        contribuicoes = self.db.table("meta_contribuicoes").select("*").eq("meta_id", meta_id).order("data", desc=True).execute()
        contribs = contribuicoes.data or []

        valor_alvo = float(meta.get("valor_alvo", 0))
        valor_atual = float(meta.get("valor_atual", 0))

        # Map PF contribution rows → seed Contribution value objects (skip rows
        # missing a parseable date — the seed projection tolerates an empty list).
        seed_contribs: list[Contribution] = []
        for c in contribs:
            raw_date = c.get("data") or ""
            try:
                at = date.fromisoformat(raw_date[:10])
            except ValueError:
                # Row has no usable date — exclude from projection but keep in
                # response payload (tests rely on count of contribuicoes).
                continue
            seed_contribs.append(Contribution(amount=float(c.get("valor", 0)), at=at))

        progress = compute_progress(
            target=Target(valor_alvo),
            current=valor_atual,
            contributions=seed_contribs,
            today=date.today(),
        )

        data_previsao = (
            progress.projected_completion_date.isoformat()
            if progress.projected_completion_date is not None
            else None
        )

        return {
            "meta": meta,
            "percentual": progress.percent_complete,
            "faltam": progress.remaining,
            "data_previsao": data_previsao,
            "contribuicoes": contribs,
        }
