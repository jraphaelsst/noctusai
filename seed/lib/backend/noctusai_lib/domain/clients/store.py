"""`ClientsStore` -- the persistence port of the clients organ (Protocol + in-memory Fake + shared filter rule).

Every method takes the `org_id` and filters by it: an id from another org is indistinguishable from a missing one.
Rows are plain dicts shaped like the DDL (`sql.clients_table_ddl`) carrying JSON-ready values: instants are ISO-8601
strings in UTC (`+00:00`), dates `YYYY-MM-DD`, the schedule's `slot_time` `HH:MM:SS`. The service writes them in
that form, so the Fake and the Real store compare the same strings the database compares.

Search (`ClientFilters.q`) is the leads rule (`leads.store.parse_search`): text matches name / email / phone
(case-insensitive substring), and a digits-only-ish term also matches the stored E.164 phone's digits.

Every multi-row read is bounded: the Real store pages past PostgREST's 1 000-row cap and batches `in_()` lists
(`table_reads.paged_rows` / `in_batched_rows`); the Fake has no cap but the same semantics.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol, Sequence, runtime_checkable
from uuid import uuid4

from noctusai_lib.domain.leads.store import parse_search

from .errors import ClientConflictError

_NON_DIGITS = re.compile(r"\D")


@dataclass(frozen=True)
class ClientFilters:
    q: Optional[str] = None
    status: Optional[str] = None
    tag: Optional[str] = None
    lead_id: Optional[str] = None


def client_matches(row: dict, f: ClientFilters) -> bool:
    """The filter semantics in Python (Fake store + tests); the Real store expresses the same in PostgREST."""
    if f.status and row.get("status") != f.status:
        return False
    if f.tag and f.tag not in (row.get("tags") or []):
        return False
    if f.lead_id and str(row.get("lead_id") or "") != str(f.lead_id):
        return False
    text, digits = parse_search(f.q)
    if text:
        low = text.lower()
        hit = any(low in str(row.get(c) or "").lower() for c in ("name", "email", "phone"))
        if not hit and digits:
            hit = digits in _NON_DIGITS.sub("", str(row.get("phone") or ""))
        if not hit:
            return False
    return True


def client_sort_key(row: dict):
    return (str(row.get("name") or "").lower(), str(row.get("id") or ""))


def session_sort_key(row: dict):
    return (str(row.get("starts_at") or ""), str(row.get("id") or ""))


@runtime_checkable
class ClientsStore(Protocol):
    """Persistence port. Implemented by `FakeClientsStore` and `SupabaseClientsStore`."""

    # -- clients
    def get_client(self, org_id: str, client_id: str) -> Optional[dict]: ...

    def client_by_lead(self, org_id: str, lead_id: str) -> Optional[dict]: ...

    def insert_client(self, org_id: str, row: dict) -> dict:
        """Persist `row`. Raises `ClientConflictError` when a client for the same `lead_id` exists."""

    def update_client(self, org_id: str, client_id: str, patch: dict) -> Optional[dict]: ...

    def delete_client(self, org_id: str, client_id: str) -> bool:
        """Delete the client (its schedules and sessions cascade)."""

    def query_clients(self, org_id: str, filters: ClientFilters, *, limit: int, offset: int = 0) -> list[dict]:
        """Name ascending (case-insensitive in the Fake, collation order in the DB), ties by id."""

    def clients_by_ids(self, org_id: str, client_ids: Iterable[str]) -> list[dict]: ...

    def all_tags(self, org_id: str) -> list[str]:
        """Distinct tags used by the org's clients, sorted."""

    # -- schedules
    def get_schedule(self, org_id: str, schedule_id: str) -> Optional[dict]: ...

    def insert_schedule(self, org_id: str, row: dict) -> dict: ...

    def update_schedule(self, org_id: str, schedule_id: str, patch: dict) -> Optional[dict]: ...

    def delete_schedule(self, org_id: str, schedule_id: str) -> bool: ...

    def schedules_of_client(self, org_id: str, client_id: str) -> list[dict]:
        """Oldest first (created_at, id)."""

    def schedules_due(self, org_id: str, through: str, *, client_id: Optional[str] = None) -> list[dict]:
        """ACTIVE schedules whose `materialized_until` is NULL or before `through` (YYYY-MM-DD)."""

    # -- sessions
    def get_session(self, org_id: str, session_id: str) -> Optional[dict]: ...

    def insert_session(self, org_id: str, row: dict) -> dict: ...

    def insert_generated_sessions(self, org_id: str, rows: Sequence[dict]) -> list[dict]:
        """Insert schedule-generated sessions, IGNORING any whose `(schedule_id, starts_at)` exists (the unique
        guard). Returns only the rows actually inserted."""

    def update_session(self, org_id: str, session_id: str, patch: dict) -> Optional[dict]: ...

    def delete_sessions(self, org_id: str, session_ids: Sequence[str]) -> int: ...

    def sessions_between(
        self, org_id: str, start: str, end: str, *, client_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        """`start <= starts_at < end` (ISO instants), ascending (starts_at, id)."""

    def sessions_of_clients(self, org_id: str, client_ids: Sequence[str]) -> list[dict]:
        """Every session of these clients (any time), ascending."""

    def sessions_of_schedule_after(self, org_id: str, schedule_id: str, after: str) -> list[dict]:
        """Sessions generated by `schedule_id` with `starts_at > after`, ascending."""

    def booked_sessions_of_client(self, org_id: str, client_id: str) -> list[dict]:
        """Sessions of the client carrying a finance receivable (`entry_id` not null)."""

    # -- payments
    def insert_payment(self, org_id: str, row: dict) -> dict: ...

    def update_payment(self, org_id: str, payment_id: str, patch: dict) -> Optional[dict]: ...

    def delete_payment(self, org_id: str, payment_id: str) -> bool:
        """Only for a payment record that produced NO settlement (a refused first settle)."""


_TABLES = ("clients", "schedules", "sessions", "payments")


@dataclass
class FakeClientsStore:
    """In-memory `ClientsStore` -- same contract as the real one (org-scoped, unique lead + slot guards, cascades)."""

    tables: dict[str, dict[str, dict]] = field(default_factory=lambda: {t: {} for t in _TABLES})

    # -- plumbing
    def _own(self, table: str, org_id: str) -> list[dict]:
        return [r for r in self.tables[table].values() if r["org_id"] == str(org_id)]

    def _get(self, table: str, org_id: str, row_id: str) -> Optional[dict]:
        r = self.tables[table].get(str(row_id))
        return deepcopy(r) if r and r["org_id"] == str(org_id) else None

    def _insert(self, table: str, org_id: str, row: dict) -> dict:
        row = deepcopy(row)
        now = datetime.now(timezone.utc).isoformat()
        row.setdefault("id", str(uuid4()))
        row["org_id"] = str(org_id)
        row.setdefault("created_at", now)
        if table != "payments":
            row.setdefault("updated_at", now)
        self.tables[table][row["id"]] = row
        return deepcopy(row)

    def _update(self, table: str, org_id: str, row_id: str, patch: dict) -> Optional[dict]:
        r = self.tables[table].get(str(row_id))
        if not r or r["org_id"] != str(org_id):
            return None
        r.update(deepcopy(patch))
        return deepcopy(r)

    # -- clients
    def get_client(self, org_id: str, client_id: str) -> Optional[dict]:
        return self._get("clients", org_id, client_id)

    def client_by_lead(self, org_id: str, lead_id: str) -> Optional[dict]:
        hit = next((r for r in self._own("clients", org_id) if str(r.get("lead_id") or "") == str(lead_id)), None)
        return deepcopy(hit) if hit else None

    def insert_client(self, org_id: str, row: dict) -> dict:
        if row.get("lead_id") and self.client_by_lead(org_id, row["lead_id"]):
            raise ClientConflictError(f"client for lead {row['lead_id']!r} already exists")
        return self._insert("clients", org_id, row)

    def update_client(self, org_id: str, client_id: str, patch: dict) -> Optional[dict]:
        if patch.get("lead_id"):
            other = self.client_by_lead(org_id, patch["lead_id"])
            if other and other["id"] != str(client_id):
                raise ClientConflictError(f"client for lead {patch['lead_id']!r} already exists")
        return self._update("clients", org_id, client_id, patch)

    def delete_client(self, org_id: str, client_id: str) -> bool:
        if self.get_client(org_id, client_id) is None:
            return False
        if any(p["client_id"] == str(client_id) for p in self._own("payments", org_id)):
            raise RuntimeError("client has payments (ON DELETE RESTRICT)")
        del self.tables["clients"][str(client_id)]
        for t in ("schedules", "sessions"):
            for rid in [r["id"] for r in self._own(t, org_id) if r["client_id"] == str(client_id)]:
                del self.tables[t][rid]
        return True

    def query_clients(self, org_id: str, filters: ClientFilters, *, limit: int, offset: int = 0) -> list[dict]:
        rows = sorted((r for r in self._own("clients", org_id) if client_matches(r, filters)), key=client_sort_key)
        return deepcopy(rows[offset : offset + limit])

    def clients_by_ids(self, org_id: str, client_ids: Iterable[str]) -> list[dict]:
        wanted = {str(i) for i in client_ids}
        return deepcopy([r for r in self._own("clients", org_id) if r["id"] in wanted])

    def all_tags(self, org_id: str) -> list[str]:
        return sorted({t for r in self._own("clients", org_id) for t in (r.get("tags") or [])})

    # -- schedules
    def get_schedule(self, org_id: str, schedule_id: str) -> Optional[dict]:
        return self._get("schedules", org_id, schedule_id)

    def insert_schedule(self, org_id: str, row: dict) -> dict:
        return self._insert("schedules", org_id, row)

    def update_schedule(self, org_id: str, schedule_id: str, patch: dict) -> Optional[dict]:
        return self._update("schedules", org_id, schedule_id, patch)

    def delete_schedule(self, org_id: str, schedule_id: str) -> bool:
        if self.get_schedule(org_id, schedule_id) is None:
            return False
        del self.tables["schedules"][str(schedule_id)]
        for r in self._own("sessions", org_id):
            if r.get("schedule_id") == str(schedule_id):
                r["schedule_id"] = None  # ON DELETE SET NULL
        return True

    def schedules_of_client(self, org_id: str, client_id: str) -> list[dict]:
        rows = [r for r in self._own("schedules", org_id) if r["client_id"] == str(client_id)]
        return deepcopy(sorted(rows, key=lambda r: (str(r.get("created_at")), r["id"])))

    def schedules_due(self, org_id: str, through: str, *, client_id: Optional[str] = None) -> list[dict]:
        rows = [
            r for r in self._own("schedules", org_id)
            if r.get("active") and (r.get("materialized_until") is None or str(r["materialized_until"]) < through)
            and (client_id is None or r["client_id"] == str(client_id))
        ]
        return deepcopy(sorted(rows, key=lambda r: r["id"]))

    # -- sessions
    def get_session(self, org_id: str, session_id: str) -> Optional[dict]:
        return self._get("sessions", org_id, session_id)

    def insert_session(self, org_id: str, row: dict) -> dict:
        return self._insert("sessions", org_id, row)

    def insert_generated_sessions(self, org_id: str, rows: Sequence[dict]) -> list[dict]:
        taken = {(r.get("schedule_id"), r.get("starts_at")) for r in self.tables["sessions"].values() if r.get("schedule_id")}
        out = []
        for row in rows:
            key = (row.get("schedule_id"), row.get("starts_at"))
            if key in taken:
                continue
            taken.add(key)
            out.append(self._insert("sessions", org_id, row))
        return out

    def update_session(self, org_id: str, session_id: str, patch: dict) -> Optional[dict]:
        return self._update("sessions", org_id, session_id, patch)

    def delete_sessions(self, org_id: str, session_ids: Sequence[str]) -> int:
        n = 0
        for sid in session_ids:
            r = self.tables["sessions"].get(str(sid))
            if r and r["org_id"] == str(org_id):
                del self.tables["sessions"][str(sid)]
                n += 1
        return n

    def sessions_between(
        self, org_id: str, start: str, end: str, *, client_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        rows = [
            r for r in self._own("sessions", org_id)
            if start <= str(r["starts_at"]) < end
            and (client_id is None or r["client_id"] == str(client_id))
            and (status is None or r["status"] == status)
        ]
        return deepcopy(sorted(rows, key=session_sort_key))

    def sessions_of_clients(self, org_id: str, client_ids: Sequence[str]) -> list[dict]:
        wanted = {str(i) for i in client_ids}
        return deepcopy(sorted((r for r in self._own("sessions", org_id) if r["client_id"] in wanted), key=session_sort_key))

    def sessions_of_schedule_after(self, org_id: str, schedule_id: str, after: str) -> list[dict]:
        rows = [r for r in self._own("sessions", org_id) if r.get("schedule_id") == str(schedule_id) and str(r["starts_at"]) > after]
        return deepcopy(sorted(rows, key=session_sort_key))

    def booked_sessions_of_client(self, org_id: str, client_id: str) -> list[dict]:
        rows = [r for r in self._own("sessions", org_id) if r["client_id"] == str(client_id) and r.get("entry_id")]
        return deepcopy(sorted(rows, key=session_sort_key))

    # -- payments
    def insert_payment(self, org_id: str, row: dict) -> dict:
        return self._insert("payments", org_id, row)

    def update_payment(self, org_id: str, payment_id: str, patch: dict) -> Optional[dict]:
        return self._update("payments", org_id, payment_id, patch)

    def delete_payment(self, org_id: str, payment_id: str) -> bool:
        r = self.tables["payments"].get(str(payment_id))
        if not r or r["org_id"] != str(org_id):
            return False
        del self.tables["payments"][str(payment_id)]
        return True


__all__ = ["ClientFilters", "ClientsStore", "FakeClientsStore", "client_matches", "client_sort_key", "session_sort_key"]
