"""Lancamentos (cashflow) service — CONTRACT.md §Cashflow + dashboard,
slice BE-C.

Reads page through `iter_paged_rows` rather than a bare unbounded
`.select().execute()` (KB § PATTERNS/backend/postgrest-row-cap.md):
`lancamentos` accumulates one row per manual entry AND every payment /
refund the webhooks book, so a 24-month `GET` can legitimately cross
PostgREST's 1 000-row page cap. `.order("id")` is required for
`iter_paged_rows`'s progress guard; the in-repo `MockSupabaseClient`
still treats `.order()` as a no-op for actual SORTING (same rationale
`membros_service`/`planos_service` document) — display ordering and
pagination are applied in Python below.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.schemas.lancamentos import DEFAULT_CATEGORIAS

_TABLE = "lancamentos"
_MEMBROS_TABLE = "membros"


class LancamentosServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _iso(value: Any) -> Any:
    """Stringify a `date`/`datetime` payload value before a write — the
    real PostgREST client cannot JSON-encode either (see
    `noctusai_lib.testing.mocks._validate_json_serializable`)."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class LancamentosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    def _fetch_filtered(
        self, *, de: date, ate: date, tipo: str | None, categoria: str | None,
    ) -> list[dict]:
        def _page(start: int, end: int):
            query = (
                self._client.table(_TABLE).select("*")
                .eq("org_id", self._org_id)
                .gte("data", de.isoformat())
                .lte("data", ate.isoformat())
            )
            if tipo:
                query = query.eq("tipo", tipo)
            if categoria:
                query = query.eq("categoria", categoria)
            return query.order("id").range(start, end).execute().data

        return list(iter_paged_rows(_page, label=f"lancamentos org={self._org_id}"))

    async def list(
        self,
        *,
        de: date,
        ate: date,
        tipo: str | None = None,
        categoria: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        rows = self._fetch_filtered(de=de, ate=ate, tipo=tipo, categoria=categoria)
        totais = self._compute_totais(rows)
        # Newest first — the CRM/cashflow-list convention every sibling
        # module-1/2 router already follows for its own listing.
        rows.sort(key=lambda r: (r.get("data") or "", r.get("created_at") or ""), reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        membro_nomes = self._membro_nomes([r.get("membro_id") for r in page_rows])
        items = [self._to_out(r, membro_nomes) for r in page_rows]
        return {"items": items, "total": total, "totais": totais}

    @staticmethod
    def _compute_totais(rows: list[dict]) -> dict[str, int]:
        entradas = sum(r["valor_centavos"] for r in rows if r.get("tipo") == "entrada")
        saidas = sum(r["valor_centavos"] for r in rows if r.get("tipo") == "saida")
        return {
            "entradas_centavos": entradas,
            "saidas_centavos": saidas,
            "saldo_centavos": entradas - saidas,
        }

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
        membro_id = row.get("membro_id")
        return {**row, "membro_nome": membro_nomes.get(str(membro_id)) if membro_id else None}

    async def categorias(self) -> list[str]:
        """Distinct categories ever used ∪ the contract's default set,
        sorted for a deterministic response."""
        def _page(start: int, end: int):
            return (
                self._client.table(_TABLE).select("id,categoria")
                .eq("org_id", self._org_id)
                .order("id").range(start, end).execute().data
            )

        rows = list(iter_paged_rows(_page, label=f"lancamentos categorias org={self._org_id}"))
        used = {r["categoria"] for r in rows if r.get("categoria")}
        return sorted(used | set(DEFAULT_CATEGORIAS))

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()),
            **{k: _iso(v) for k, v in payload.items()},
            "org_id": self._org_id,
            "origem": "manual",
            "created_at": now,
            "updated_at": now,
        }
        result = self._client.table(_TABLE).insert(row).execute()
        if not result.data:
            raise LancamentosServiceError("Falha ao criar lançamento.")
        created = result.data[0]
        return self._to_out(created, {})

    async def _get_manual_or_raise(self, *, lancamento_id: str) -> dict | None:
        """Fetch the row; 409 when it exists but isn't `origem='manual'`
        (contract §Cashflow: "Lançamentos automáticos não podem ser
        alterados."). None only when the row itself doesn't exist."""
        current = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(lancamento_id))
            .maybe_single()
            .execute()
        ).data
        if not current:
            return None
        if current.get("origem") != "manual":
            raise LancamentosServiceError(
                "Lançamentos automáticos não podem ser alterados.", status_code=409,
            )
        return current

    async def update(self, *, lancamento_id: str, payload: dict) -> dict | None:
        current = await self._get_manual_or_raise(lancamento_id=lancamento_id)
        if current is None:
            return None
        data = {k: _iso(v) for k, v in payload.items()}
        result = (
            self._client.table(_TABLE)
            .update(data)
            .eq("org_id", self._org_id)
            .eq("id", str(lancamento_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        membro_nomes = self._membro_nomes([row.get("membro_id")])
        return self._to_out(row, membro_nomes)

    async def delete(self, *, lancamento_id: str) -> bool:
        current = await self._get_manual_or_raise(lancamento_id=lancamento_id)
        if current is None:
            return False
        result = (
            self._client.table(_TABLE)
            .delete()
            .eq("org_id", self._org_id)
            .eq("id", str(lancamento_id))
            .execute()
        )
        return bool(result.data)
