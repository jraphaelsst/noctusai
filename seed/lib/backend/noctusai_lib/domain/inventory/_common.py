"""Shared plumbing: the org `Scope`, row helpers, decimal quantities.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query is filtered by that org, so an
id from another org is indistinguishable from a missing one (404). RLS is the floor, never the only check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.responses import calculate_pagination

from .config import InventoryConfig
from .errors import not_found


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def first(response: Any) -> Optional[dict]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return dict(data[0]) if data else None
    return dict(data) if isinstance(data, dict) else None


def dec(value: Any) -> Decimal:
    """A PostgREST numeric (float / str / int / None) -> exact `Decimal` (via `str`, never the float repr)."""
    if value is None or value == "":
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def qty_str(value: Any) -> str:
    """A quantity as the string the RPC casts to `numeric` (JSON has no Decimal; a float would round)."""
    return format(dec(value), "f")


@dataclass(frozen=True)
class Scope:
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    db: Any
    cfg: InventoryConfig
    org_id: str

    def tbl(self, name: str):
        return self.db.table(self.cfg.table(name))

    def find(self, name: str, row_id: Any, *, col: str = "id") -> Optional[dict]:
        resp = self.tbl(name).select("*").eq("org_id", self.org_id).eq(col, str(row_id)).limit(1).execute()
        return first(resp)

    def get(self, name: str, row_id: Any, *, what: str) -> dict:
        row = self.find(name, row_id)
        if row is None:
            raise not_found(what)
        return row

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
        order: Iterable[tuple[str, bool]] = (("id", False),),
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


__all__ = ["Scope", "dec", "first", "new_id", "now_iso", "qty_str"]
