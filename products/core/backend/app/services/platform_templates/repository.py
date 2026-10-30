"""Persistence for ``public.platform_templates`` (core migration 092).

SYNC methods (the router runs them off the event loop). Bare table names -- the admin client
already targets ``public``. ``FakePlatformTemplateRepo`` is the in-memory twin carrying the
migration's invariants (version uniqueness, one active per scope, frozen non-drafts, activation RPC).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

TABLE = "platform_templates"
ACTIVATE_RPC = "platform_template_activate"
#: Filter value meaning "platform-wide" (product IS NULL).
PLATFORM_SCOPE = "_platform"
LIST_COLUMNS = (
    "id, product, kind, key, title, description, format, version, status, "
    "created_by, updated_by, created_at, updated_at, activated_at"
)


class NotFound(Exception):
    """Unknown id."""


class VersionConflict(Exception):
    """Two writers raced for the same (product, kind, key, version)."""


class FrozenVersion(Exception):
    """A non-draft version cannot be edited in place."""


class PlatformTemplateRepo(Protocol):
    def list(self, *, product: Optional[str], kind: Optional[str]) -> list[dict]: ...
    def get(self, template_id: str) -> Optional[dict]: ...
    def history(self, product: Optional[str], kind: str, key: str) -> list[dict]: ...
    def next_version(self, product: Optional[str], kind: str, key: str) -> int: ...
    def insert(self, row: dict) -> dict: ...
    def update_draft(self, template_id: str, fields: dict) -> Optional[dict]: ...
    def activate(self, template_id: str) -> dict: ...
    def archive(self, template_id: str, updated_by: Optional[str]) -> Optional[dict]: ...


def _first(data: Any) -> Optional[dict]:
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


def _scope(q: Any, product: Optional[str]) -> Any:
    return q.is_("product", "null") if product is None else q.eq("product", product)


class SupabasePlatformTemplateRepo:
    def __init__(self, client: Any) -> None:
        self._c = client

    def list(self, *, product: Optional[str], kind: Optional[str]) -> list[dict]:
        def page(start: int, end: int):
            q = self._c.table(TABLE).select(LIST_COLUMNS)
            if product is not None:
                q = q.is_("product", "null") if product == PLATFORM_SCOPE else q.eq("product", product)
            if kind:
                q = q.eq("kind", kind)
            return q.order("id").range(start, end).execute().data

        return list(iter_paged_rows(page, label=TABLE))

    def get(self, template_id: str) -> Optional[dict]:
        return _first(self._c.table(TABLE).select("*").eq("id", template_id).limit(1).execute().data)

    def history(self, product: Optional[str], kind: str, key: str) -> list[dict]:
        q = self._c.table(TABLE).select(LIST_COLUMNS).eq("kind", kind).eq("key", key)
        rows = _scope(q, product).order("version", desc=True).execute().data or []
        return rows

    def next_version(self, product: Optional[str], kind: str, key: str) -> int:
        q = self._c.table(TABLE).select("version").eq("kind", kind).eq("key", key)
        row = _first(_scope(q, product).order("version", desc=True).limit(1).execute().data)
        return int(row["version"]) + 1 if row else 1

    def insert(self, row: dict) -> dict:
        try:
            return _first(self._c.table(TABLE).insert(row).execute().data) or row
        except Exception as exc:
            if is_unique_violation(exc):
                raise VersionConflict(str(row.get("version"))) from exc
            raise

    def update_draft(self, template_id: str, fields: dict) -> Optional[dict]:
        res = self._c.table(TABLE).update(fields).eq("id", template_id).eq("status", "draft").execute()
        return _first(res.data)

    def activate(self, template_id: str) -> dict:
        try:
            res = self._c.rpc(ACTIVATE_RPC, {"p_id": template_id}).execute()
        except Exception as exc:
            if f"{ACTIVATE_RPC}:not_found" in str(exc):
                raise NotFound(template_id) from exc
            raise
        row = _first(res.data)
        if row is None:
            raise NotFound(template_id)
        return row

    def archive(self, template_id: str, updated_by: Optional[str]) -> Optional[dict]:
        res = (
            self._c.table(TABLE)
            .update({"status": "archived", "updated_by": updated_by, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", template_id).in_("status", ["draft", "active"]).execute()
        )
        return _first(res.data)


class FakePlatformTemplateRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def seed(self, **fields: Any) -> dict:
        return self.insert({"status": "active", "version": 1, "description": "", **fields})

    @staticmethod
    def _same_scope(r: dict, product: Optional[str], kind: str, key: str) -> bool:
        return r["product"] == product and r["kind"] == kind and r["key"] == key

    def list(self, *, product: Optional[str], kind: Optional[str]) -> list[dict]:
        keep = {c.strip() for c in LIST_COLUMNS.split(",")}
        out = []
        for r in self.rows.values():
            if product == PLATFORM_SCOPE and r["product"] is not None:
                continue
            if product not in (None, PLATFORM_SCOPE) and r["product"] != product:
                continue
            if kind and r["kind"] != kind:
                continue
            out.append({k: v for k, v in copy.deepcopy(r).items() if k in keep})
        return out

    def get(self, template_id: str) -> Optional[dict]:
        r = self.rows.get(template_id)
        return copy.deepcopy(r) if r else None

    def history(self, product: Optional[str], kind: str, key: str) -> list[dict]:
        keep = {c.strip() for c in LIST_COLUMNS.split(",")}
        rows = [{k: v for k, v in copy.deepcopy(r).items() if k in keep}
                for r in self.rows.values() if self._same_scope(r, product, kind, key)]
        return sorted(rows, key=lambda r: r["version"], reverse=True)

    def next_version(self, product: Optional[str], kind: str, key: str) -> int:
        versions = [r["version"] for r in self.rows.values() if self._same_scope(r, product, kind, key)]
        return max(versions) + 1 if versions else 1

    def insert(self, row: dict) -> dict:
        if any(self._same_scope(r, row.get("product"), row["kind"], row["key"]) and r["version"] == row["version"]
               for r in self.rows.values()):
            raise VersionConflict(str(row["version"]))
        full = {"product": None, "description": "", "status": "draft", "created_by": None, "updated_by": None,
                "created_at": self._now(), "updated_at": self._now(), "activated_at": None, **copy.deepcopy(row)}
        full.setdefault("id", str(uuid.uuid4()))
        if full["status"] == "active":
            full["activated_at"] = full["activated_at"] or self._now()
        self.rows[full["id"]] = full
        return copy.deepcopy(full)

    def update_draft(self, template_id: str, fields: dict) -> Optional[dict]:
        r = self.rows.get(template_id)
        if not r or r["status"] != "draft":
            return None
        r.update(copy.deepcopy(fields))
        return copy.deepcopy(r)

    def activate(self, template_id: str) -> dict:
        r = self.rows.get(template_id)
        if not r:
            raise NotFound(template_id)
        if r["status"] != "active":
            for other in self.rows.values():
                if self._same_scope(other, r["product"], r["kind"], r["key"]) and other["status"] == "active":
                    other["status"] = "archived"
            r["status"], r["activated_at"], r["updated_at"] = "active", self._now(), self._now()
        return copy.deepcopy(r)

    def archive(self, template_id: str, updated_by: Optional[str]) -> Optional[dict]:
        r = self.rows.get(template_id)
        if not r or r["status"] not in ("draft", "active"):
            return None
        r.update(status="archived", updated_by=updated_by, updated_at=self._now())
        return copy.deepcopy(r)
