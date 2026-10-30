"""Persistence for ``public.org_brand_identities`` (core migration 089).

SYNC methods (the service runs them off the event loop). Every read/write of an
org row is scoped by ``org_id`` in the query itself — an id from another org is
indistinguishable from a missing one (→ 404 upstream). Table names are BARE
(the admin client already targets ``public``).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

TABLE = "org_brand_identities"
ACTIVATE_RPC = "brand_identity_activate"
#: Columns safe for listings / the browser-facing read (no voice/source/brand_book).
LIST_COLUMNS = "id, org_id, version, status, tokens, assets, validation, created_by, created_at, activated_at"
CURRENT_COLUMNS = "id, org_id, version, status, tokens, assets, created_at, activated_at"


class ActivationRefused(Exception):
    """``codigo`` ∈ {not_found, invalid_status}."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class VersionConflict(Exception):
    """Two drafts raced for the same ``(org_id, version)``."""


class BrandRepo(Protocol):
    def active(self, org_id: Optional[str], columns: str = CURRENT_COLUMNS) -> Optional[dict]: ...
    def list_for(self, org_id: str) -> list[dict]: ...
    def get(self, identity_id: str, org_id: str) -> Optional[dict]: ...
    def next_version(self, org_id: str) -> int: ...
    def insert(self, row: dict) -> dict: ...
    def update(self, identity_id: str, org_id: str, fields: dict, *, statuses: Iterable[str]) -> Optional[dict]: ...
    def activate(self, identity_id: str, org_id: str) -> dict: ...
    def find_by_job(self, job_id: str, org_id: str) -> Optional[dict]: ...


def _first(data: Any) -> Optional[dict]:
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


class SupabaseBrandRepo:
    def __init__(self, client: Any) -> None:
        self._c = client

    def active(self, org_id: Optional[str], columns: str = CURRENT_COLUMNS) -> Optional[dict]:
        q = self._c.table(TABLE).select(columns).eq("status", "active")
        q = q.is_("org_id", "null") if org_id is None else q.eq("org_id", org_id)
        return _first(q.limit(1).execute().data)

    def list_for(self, org_id: str) -> list[dict]:
        def page(start: int, end: int):
            return (
                self._c.table(TABLE).select(LIST_COLUMNS).eq("org_id", org_id)
                .order("id").range(start, end).execute().data
            )

        rows = list(iter_paged_rows(page, label=TABLE))
        return sorted(rows, key=lambda r: int(r.get("version") or 0), reverse=True)

    def get(self, identity_id: str, org_id: str) -> Optional[dict]:
        return _first(
            self._c.table(TABLE).select("*").eq("id", identity_id).eq("org_id", org_id).limit(1).execute().data
        )

    def next_version(self, org_id: str) -> int:
        row = _first(
            self._c.table(TABLE).select("version").eq("org_id", org_id)
            .order("version", desc=True).limit(1).execute().data
        )
        return int(row["version"]) + 1 if row else 1

    def insert(self, row: dict) -> dict:
        try:
            return _first(self._c.table(TABLE).insert(row).execute().data) or row
        except Exception as exc:
            if is_unique_violation(exc):
                raise VersionConflict(str(row.get("version"))) from exc
            raise

    def update(self, identity_id: str, org_id: str, fields: dict, *, statuses: Iterable[str]) -> Optional[dict]:
        res = (
            self._c.table(TABLE).update(fields).eq("id", identity_id).eq("org_id", org_id)
            .in_("status", list(statuses)).execute()
        )
        return _first(res.data)

    def activate(self, identity_id: str, org_id: str) -> dict:
        try:
            res = self._c.rpc(ACTIVATE_RPC, {"p_identity_id": identity_id, "p_org_id": org_id}).execute()
        except Exception as exc:
            text = str(exc)
            for codigo in ("not_found", "invalid_status"):
                if f"brand_identity_activate:{codigo}" in text:
                    raise ActivationRefused(codigo) from exc
            raise
        row = _first(res.data)
        if row is None:
            raise ActivationRefused("not_found")
        return row

    def find_by_job(self, job_id: str, org_id: str) -> Optional[dict]:
        """The identity an ingestion job belongs to (``source.extraction.job_id``), org-scoped."""
        return _first(
            self._c.table(TABLE).select("id, org_id, status, source").eq("org_id", org_id)
            .eq("source->extraction->>job_id", job_id).limit(1).execute().data
        )


class FakeBrandRepo:
    """In-memory twin of :class:`SupabaseBrandRepo` + migration 089's invariants
    (partial uniques, activation RPC)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def seed_platform(self, tokens: dict) -> dict:
        row = {"id": str(uuid.uuid4()), "org_id": None, "version": 1, "status": "active",
               "tokens": tokens, "brand_book": "", "voice": {}, "assets": {}, "source": {},
               "validation": {}, "created_by": None, "created_at": self._now(), "activated_at": self._now()}
        self.rows[row["id"]] = row
        return row

    def active(self, org_id: Optional[str], columns: str = CURRENT_COLUMNS) -> Optional[dict]:
        for r in self.rows.values():
            if r["org_id"] == org_id and r["status"] == "active":
                return copy.deepcopy(r)
        return None

    def list_for(self, org_id: str) -> list[dict]:
        keep = {c.strip() for c in LIST_COLUMNS.split(",")}
        rows = [{k: v for k, v in r.items() if k in keep} for r in self.rows.values() if r["org_id"] == org_id]
        return sorted(copy.deepcopy(rows), key=lambda r: r["version"], reverse=True)

    def get(self, identity_id: str, org_id: str) -> Optional[dict]:
        r = self.rows.get(identity_id)
        return copy.deepcopy(r) if r and r["org_id"] == org_id else None

    def next_version(self, org_id: str) -> int:
        versions = [r["version"] for r in self.rows.values() if r["org_id"] == org_id]
        return max(versions) + 1 if versions else 1

    def insert(self, row: dict) -> dict:
        if any(r["org_id"] == row["org_id"] and r["version"] == row["version"] for r in self.rows.values()):
            raise VersionConflict(str(row["version"]))
        full = {"brand_book": "", "voice": {}, "assets": {}, "source": {}, "validation": {},
                "created_at": self._now(), "activated_at": None, **copy.deepcopy(row)}
        full.setdefault("id", str(uuid.uuid4()))
        self.rows[full["id"]] = full
        return copy.deepcopy(full)

    def update(self, identity_id: str, org_id: str, fields: dict, *, statuses: Iterable[str]) -> Optional[dict]:
        r = self.rows.get(identity_id)
        if not r or r["org_id"] != org_id or r["status"] not in set(statuses):
            return None
        r.update(copy.deepcopy(fields))
        return copy.deepcopy(r)

    def activate(self, identity_id: str, org_id: str) -> dict:
        r = self.rows.get(identity_id)
        if not r or r["org_id"] != org_id:
            raise ActivationRefused("not_found")
        if r["status"] == "active":
            return copy.deepcopy(r)
        if r["status"] not in ("draft", "archived"):
            raise ActivationRefused("invalid_status")
        for other in self.rows.values():
            if other["org_id"] == org_id and other["status"] == "active":
                other["status"] = "archived"
        r["status"], r["activated_at"] = "active", self._now()
        return copy.deepcopy(r)

    def find_by_job(self, job_id: str, org_id: str) -> Optional[dict]:
        for r in self.rows.values():
            if r["org_id"] == org_id and ((r.get("source") or {}).get("extraction") or {}).get("job_id") == job_id:
                return copy.deepcopy(r)
        return None
