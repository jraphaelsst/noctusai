"""Pagamentos service — contract §Manager+member views, amendment A16
(admin-only, enforced at the router).

Sort/pagination applied in Python after a scoped fetch — same rationale
every sibling module-1/module-2 service documents.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

_TABLE = "pagamentos"
_MEMBROS_TABLE = "membros"


class PagamentosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    async def list(
        self,
        *,
        membro_id: Optional[str] = None,
        assinatura_id: Optional[str] = None,
        estado: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        query = self._client.table(_TABLE).select("*").eq("org_id", self._org_id)
        if membro_id:
            query = query.eq("membro_id", str(membro_id))
        if assinatura_id:
            query = query.eq("assinatura_id", str(assinatura_id))
        if estado:
            query = query.eq("estado", estado)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        membro_nomes = self._membro_nomes([r.get("membro_id") for r in page_rows])
        items = [self._to_out(r, membro_nomes) for r in page_rows]
        return {"items": items, "total": total}

    def _membro_nomes(self, membro_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in membro_ids if i})
        if not ids:
            return {}
        rows = (
            self._client.table(_MEMBROS_TABLE)
            .select("id,nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r["nome"] for r in rows}

    @staticmethod
    def _to_out(row: dict, membro_nomes: dict[str, str]) -> dict:
        return {**row, "membro_nome": membro_nomes.get(str(row.get("membro_id")))}
