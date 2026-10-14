"""Shared plumbing for the items services: the org `Scope` and row helpers.

Every query is filtered by `org_id`, so an id from another org is indistinguishable from a missing one
(404). RLS is the floor, never the only check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.responses import calculate_pagination

from .config import ItemsConfig
from .errors import invalid, not_found


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def first(response: Any) -> Optional[dict]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return dict(data[0]) if data else None
    return dict(data) if isinstance(data, dict) else None


def like_term(q: str) -> str:
    """A safe ILIKE pattern for a user search term.

    PostgREST operator / wildcard characters from the user (`% _ , ( ) * \\ . : "`) never reach the filter
    expression; each becomes a `%` so a SKU typed as `A.B` still finds `A.B_C`.
    """
    cleaned = re.sub(r"[%_,()*\\.:\"]+", "%", (q or "").strip())
    return f"%{cleaned.strip('%')}%"


@dataclass(frozen=True)
class Scope:
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    db: Any
    cfg: ItemsConfig
    org_id: str

    def tbl(self, name: str):
        return self.db.table(self.cfg.table(name))

    def get(self, name: str, row_id: Any, *, what: str) -> dict:
        row = self.find(name, row_id)
        if row is None:
            raise not_found(what)
        return row

    def find(self, name: str, row_id: Any, *, col: str = "id") -> Optional[dict]:
        resp = self.tbl(name).select("*").eq("org_id", self.org_id).eq(col, str(row_id)).limit(1).execute()
        return first(resp)

    def rows(
        self,
        name: str,
        *,
        eq: Optional[dict] = None,
        refine: Optional[Callable[[Any], Any]] = None,
        order_col: str = "id",
    ) -> list[dict]:
        """EVERY matching row, paged past PostgREST's 1 000-row cap."""
        return paged_rows(self.db, self.cfg.table(name), self.org_id, eq_filters=eq, refine=refine, order_col=order_col)

    def page(
        self,
        name: str,
        *,
        page: int = 1,
        page_size: int = 20,
        refine: Optional[Callable[[Any], Any]] = None,
        order: Iterable[tuple[str, bool]] = (("created_at", True),),
    ) -> tuple[list[dict], int, int, int]:
        """One bounded page + the exact total: `(rows, total, page, page_size)`."""
        page, page_size, offset = calculate_pagination(page, page_size)
        query = self.tbl(name).select("*", count="exact").eq("org_id", self.org_id)
        if refine is not None:
            query = refine(query)
        for col, desc in order:
            query = query.order(col, desc=desc)
        resp = query.range(offset, offset + page_size - 1).execute()
        rows = [dict(r) for r in (resp.data or [])]
        total = getattr(resp, "count", None)
        return rows, int(total if total is not None else len(rows)), page, page_size

    def require_owned(self, name: str, row_id: Any, *, what: str, field: str) -> dict:
        """A referenced id MUST belong to this org -- beyond RLS. 422 on the field (the target exists, a reference does not)."""
        row = self.find(name, row_id)
        if row is None:
            raise invalid(field, f"{what} não encontrado(a).", code="referencia_invalida")
        return row


__all__ = ["Scope", "first", "like_term", "new_id", "now_iso"]
