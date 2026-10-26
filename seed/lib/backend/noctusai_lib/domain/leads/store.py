"""`LeadsStore` -- the persistence port of the leads organ (Protocol + in-memory Fake + shared search rule).

Every method takes the `org_id` and filters by it: an id from another org is indistinguishable from
a missing one. Rows are plain dicts shaped like the DDL (`sql.leads_table_ddl`); `position` is a
`Decimal`, timestamps are tz-aware `datetime`s on the way in and ISO strings are accepted on the way out.

Search (`LeadFilters.q`) is ONE rule shared by the Fake and the real store (`parse_search`): text matches
name / email / notes (case-insensitive substring); when the term is digits-only-ish, the DIGITS also match
the stored E.164 phone, so what the user types ("(11) 99457-3387", "99457", "+55 11 99457") finds the
number the card shows ("+5511994573387").
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Protocol, Sequence, runtime_checkable
from uuid import uuid4

from noctusai_lib.primitives.phone import phone_search_digits

from .errors import LeadConflictError

_NON_DIGITS = re.compile(r"\D")
_HAS_LETTER = re.compile(r"[^\W\d_]")
#: fewer digits than this is noise ("1"), not a phone fragment
MIN_PHONE_DIGITS = 3


@dataclass(frozen=True)
class LeadFilters:
    stage: Optional[str] = None
    origin: Optional[str] = None
    #: first-contact window (inclusive lower, exclusive upper)
    first_from: Optional[datetime] = None
    first_to: Optional[datetime] = None
    q: Optional[str] = None
    #: leads whose stage is NOT any of these (the board's "Sem etapa" column)
    stage_not_in: Optional[Sequence[str]] = None

    def without_stage(self) -> "LeadFilters":
        return replace(self, stage=None)


def parse_search(q: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """`(text, phone_digits)` for a search box value; either may be None.

    The digits clause exists only for a term without letters and with >= 3 digits -- "Rua 123" is text.
    """
    term = (q or "").strip()
    if not term:
        return None, None
    digits = None
    if not _HAS_LETTER.search(term) and len(_NON_DIGITS.sub("", term)) >= MIN_PHONE_DIGITS:
        digits = phone_search_digits(term)
    return term, digits


def matches(row: dict, f: LeadFilters) -> bool:
    """The filter semantics, in Python (Fake store + tests); the real store expresses the same in PostgREST."""
    if f.stage and row.get("stage") != f.stage:
        return False
    if f.origin and row.get("origin") != f.origin:
        return False
    if f.stage_not_in is not None and row.get("stage") in set(f.stage_not_in):
        return False
    first = as_dt(row.get("first_contact_at"))
    if f.first_from and (first is None or first < f.first_from):
        return False
    if f.first_to and (first is None or first >= f.first_to):
        return False
    text, digits = parse_search(f.q)
    if text:
        low = text.lower()
        hay = [str(row.get(c) or "").lower() for c in ("name", "email", "notes")]
        hit = any(low in h for h in hay)
        if not hit and digits:
            hit = digits in _NON_DIGITS.sub("", str(row.get("phone") or ""))
        if not hit:
            return False
    return True


def as_dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def position_of_row(row: dict) -> Decimal:
    try:
        return Decimal(str(row.get("position") if row.get("position") is not None else 0))
    except Exception:
        return Decimal(0)


def board_sort_key(row: dict):
    return (position_of_row(row), str(row.get("created_at") or ""), str(row.get("id") or ""))


def list_sort_key(row: dict):
    first = as_dt(row.get("first_contact_at")) or datetime.min.replace(tzinfo=timezone.utc)
    return (first, str(row.get("id") or ""))


@runtime_checkable
class LeadsStore(Protocol):
    """Persistence port. Implemented by `FakeLeadsStore` and `SupabaseLeadsStore`."""

    def get(self, org_id: str, lead_id: str) -> Optional[dict]: ...

    def find_by_chat(self, org_id: str, connection_id: str, chat_id: str) -> Optional[dict]: ...

    def insert(self, org_id: str, row: dict) -> dict:
        """Persist `row` (the store assigns `id` / `created_at` when absent). Raises `LeadConflictError` on a duplicate chat."""

    def update(self, org_id: str, lead_id: str, patch: dict) -> Optional[dict]: ...

    def delete(self, org_id: str, lead_id: str) -> bool: ...

    def query(self, org_id: str, filters: LeadFilters, *, limit: int, offset: int = 0) -> list[dict]:
        """Newest first contact first (ties by id). `limit` rows from `offset`."""

    def count(self, org_id: str, filters: LeadFilters) -> int: ...

    def column(self, org_id: str, stage: str, filters: LeadFilters, *, limit: int, exclude_id: Optional[str] = None) -> list[dict]:
        """The first `limit` cards of a stage, in board order (position, then created_at), optionally without one lead."""


@dataclass
class FakeLeadsStore:
    """In-memory `LeadsStore` -- same contract as the real one (org-scoped, unique chat guard)."""

    rows: dict[str, dict] = field(default_factory=dict)

    def _own(self, org_id: str) -> list[dict]:
        return [r for r in self.rows.values() if r["org_id"] == str(org_id)]

    def get(self, org_id: str, lead_id: str) -> Optional[dict]:
        r = self.rows.get(str(lead_id))
        return deepcopy(r) if r and r["org_id"] == str(org_id) else None

    def find_by_chat(self, org_id: str, connection_id: str, chat_id: str) -> Optional[dict]:
        for r in self._own(org_id):
            if r.get("whatsapp_connection_id") == str(connection_id) and r.get("whatsapp_chat_id") == chat_id:
                return deepcopy(r)
        return None

    def insert(self, org_id: str, row: dict) -> dict:
        row = deepcopy(row)
        conn, chat = row.get("whatsapp_connection_id"), row.get("whatsapp_chat_id")
        if conn and chat and self.find_by_chat(org_id, conn, chat):
            raise LeadConflictError(f"lead for chat {chat!r} already exists")
        now = datetime.now(timezone.utc)
        row.setdefault("id", str(uuid4()))
        row["org_id"] = str(org_id)
        row.setdefault("created_at", now)
        row.setdefault("updated_at", now)
        self.rows[row["id"]] = row
        return deepcopy(row)

    def update(self, org_id: str, lead_id: str, patch: dict) -> Optional[dict]:
        r = self.rows.get(str(lead_id))
        if not r or r["org_id"] != str(org_id):
            return None
        r.update(deepcopy(patch))
        return deepcopy(r)

    def delete(self, org_id: str, lead_id: str) -> bool:
        r = self.rows.get(str(lead_id))
        if not r or r["org_id"] != str(org_id):
            return False
        del self.rows[str(lead_id)]
        return True

    def query(self, org_id: str, filters: LeadFilters, *, limit: int, offset: int = 0) -> list[dict]:
        rows = sorted((r for r in self._own(org_id) if matches(r, filters)), key=list_sort_key, reverse=True)
        return deepcopy(rows[offset : offset + limit])

    def count(self, org_id: str, filters: LeadFilters) -> int:
        return sum(1 for r in self._own(org_id) if matches(r, filters))

    def column(self, org_id: str, stage: str, filters: LeadFilters, *, limit: int, exclude_id: Optional[str] = None) -> list[dict]:
        f = replace(filters, stage=stage)
        rows = sorted(
            (r for r in self._own(org_id) if matches(r, f) and r["id"] != exclude_id), key=board_sort_key
        )
        return deepcopy(rows[:limit])


__all__ = [
    "FakeLeadsStore",
    "LeadFilters",
    "LeadsStore",
    "MIN_PHONE_DIGITS",
    "as_dt",
    "board_sort_key",
    "list_sort_key",
    "matches",
    "parse_search",
    "position_of_row",
]
