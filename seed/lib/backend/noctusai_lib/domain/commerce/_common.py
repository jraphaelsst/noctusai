"""Small helpers shared by the commerce services (no IO of their own)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.primitives.responses import calculate_pagination

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def new_id() -> str:
    return str(uuid4())


def tbl(db: Any, name: str):
    """The query builder for `name` on an already schema-scoped client."""
    return db.table(name)


def first(response: Any) -> Optional[dict]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return dict(data[0]) if data else None
    return dict(data) if isinstance(data, dict) else None


def get_row(db: Any, table: str, org_id: Any, row_id: Any, *, id_col: str = "id") -> Optional[dict]:
    """One row of `table` for this org, or None. ALWAYS org-scoped: an id that
    belongs to another org is indistinguishable from a missing one."""
    resp = tbl(db, table).select("*").eq("org_id", str(org_id)).eq(id_col, str(row_id)).limit(1).execute()
    return first(resp)


def page_rows(
    db: Any,
    table: str,
    org_id: Any,
    *,
    page: int = 1,
    page_size: int = 20,
    refine: Any = None,
    order_col: str = "created_at",
    desc: bool = True,
    eq_filters: Optional[dict] = None,
) -> tuple[list[dict], int, int, int]:
    """One bounded page + the exact total: `(rows, total, page, page_size)`."""
    page, page_size, offset = calculate_pagination(page, page_size)
    query = tbl(db, table).select("*", count="exact").eq("org_id", str(org_id))
    for key, value in (eq_filters or {}).items():
        query = query.eq(key, value)
    if refine is not None:
        query = refine(query)
    resp = query.order(order_col, desc=desc).range(offset, offset + page_size - 1).execute()
    rows = [dict(r) for r in (resp.data or [])]
    total = getattr(resp, "count", None)
    return rows, int(total if total is not None else len(rows)), page, page_size


def like_term(q: str) -> str:
    """A safe ILIKE pattern for a user search term (no wildcards from the user)."""
    cleaned = re.sub(r"[%_,()*\\]", " ", q or "").strip()
    return f"%{cleaned}%"


def slugify(text: str) -> str:
    base = fold_accents_ascii(text)
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug[:80] or "item"


def valid_email(value: str) -> bool:
    return bool(value) and len(value) <= 254 and bool(_EMAIL_RE.match(value))


def digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


__all__ = [
    "digits",
    "first",
    "get_row",
    "like_term",
    "new_id",
    "now",
    "now_iso",
    "page_rows",
    "slugify",
    "tbl",
    "valid_email",
]
