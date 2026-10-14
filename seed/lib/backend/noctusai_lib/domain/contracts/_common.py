"""Shared plumbing for the contracts services: the org `Scope`.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query it issues is filtered by that
org, so an id from another org is indistinguishable from a missing one (404). RLS is the floor.

Date / id helpers are the finance organ's, imported rather than copied.
NOC-REMEDIATE[organ-common-lift]: parties / items / contracts now share this `Scope` shape --
lift it into one `domain/_organ_common` (recurrence rule N>=3; a parallel slice owns the lift). — 2026-10-14
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from noctusai_lib.domain.finance._common import add_months, first, iso, like_term, month_start, new_id, now_iso, to_date, today
from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.responses import calculate_pagination

from .config import ContractsConfig
from .errors import not_found


@dataclass(frozen=True)
class Scope:
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    db: Any
    cfg: ContractsConfig
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

    def rows(self, name: str, *, eq: Optional[dict] = None, refine: Optional[Callable[[Any], Any]] = None,
             order_col: str = "id") -> list[dict]:
        """EVERY matching row, paged past PostgREST's 1 000-row cap."""
        return paged_rows(self.db, self.cfg.table(name), self.org_id, eq_filters=eq, refine=refine, order_col=order_col)

    def page(self, name: str, *, page: int = 1, page_size: int = 20, refine: Optional[Callable[[Any], Any]] = None,
             order: Iterable[tuple[str, bool]] = (("created_at", True),)) -> tuple[list[dict], int, int, int]:
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


__all__ = ["Scope", "add_months", "first", "iso", "like_term", "month_start", "new_id", "now_iso", "to_date", "today"]
