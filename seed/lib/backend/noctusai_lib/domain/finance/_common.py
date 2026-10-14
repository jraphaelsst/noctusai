"""Shared plumbing for the finance services: the org `Scope`, row helpers, dates.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query it issues is
filtered by that org, so an id from another org is indistinguishable from a
missing one (404). RLS is the floor, never the only check (contract §0).
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.responses import calculate_pagination

from .config import FinanceConfig
from .errors import not_found


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def today() -> date:
    return now().date()


def new_id() -> str:
    return str(uuid4())


def first(response: Any) -> Optional[dict]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return dict(data[0]) if data else None
    return dict(data) if isinstance(data, dict) else None


def to_date(value: Any) -> Optional[date]:
    """`date` | ISO string (date or datetime) | None -> `date` | None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(value: Any) -> Optional[str]:
    d = to_date(value)
    return d.isoformat() if d else None


def month_start(value: Any) -> date:
    d = to_date(value)
    assert d is not None
    return d.replace(day=1)


def add_months(d: date, months: int, anchor_day: Optional[int] = None) -> date:
    """`d` + `months`, keeping `anchor_day` (default `d.day`) clamped to the month's last day.

    Anchoring matters: Jan 31 -> Feb 28 -> Mar 28 would drift; with the anchor
    kept at 31 it goes Feb 28 -> Mar 31.
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(anchor_day or d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def like_term(q: str) -> str:
    """A safe ILIKE pattern for a user search term (no wildcards / PostgREST operators from the user)."""
    cleaned = re.sub(r"[%_,()*\\.:\"]", " ", q or "").strip()
    return f"%{cleaned}%"


def digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


@dataclass(frozen=True)
class Scope:
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    db: Any
    cfg: FinanceConfig
    org_id: str

    def tbl(self, name: str):
        return self.db.table(self.cfg.table(name))

    def get(self, name: str, row_id: Any, *, what: str) -> dict:
        """One row of `name` for this org, else 404 (`what` = the pt-BR noun)."""
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
        """One bounded page + the exact total: `(rows, total, page, page_size)`.

        `order` is `(column, descending)` pairs; callers end it with `("id", ...)`
        so paging is deterministic across ties.
        """
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
        """A referenced id (account / category / ...) MUST belong to this org -- beyond RLS.

        422 on the field (not 404): the target of the request exists, one of its
        references does not.
        """
        from .errors import invalid

        row = self.find(name, row_id)
        if row is None:
            raise invalid(field, f"{what} não encontrado(a).", code="referencia_invalida")
        return row


__all__ = [
    "Scope",
    "add_months",
    "digits",
    "first",
    "iso",
    "like_term",
    "month_start",
    "new_id",
    "now",
    "now_iso",
    "to_date",
    "today",
]
