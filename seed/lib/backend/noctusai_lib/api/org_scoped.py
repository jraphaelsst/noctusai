"""Org-scoped service-role client -- tenant isolation enforced IN CODE, by construction.

**Why.** A product that reads and writes tenant tables with the service-role client (RLS bypassed, the tables are
service-only so the browser roles cannot reach them) must scope every query itself. Hand-written
``.eq("org_id", org)`` on each call is one forgotten filter away from a cross-tenant leak. This wrapper makes the
filter impossible to forget: the caller gets an :class:`OrgScopedClient` bound to ONE org (taken from the
authenticated context, never from a body or a path) and every table call goes through it.

What it enforces, for every table the wrapper touches:

* ``select`` / ``update`` / ``delete`` always carry ``.eq(org_column, org_id)``;
* ``insert`` / ``upsert`` stamp ``org_column = org_id`` on every row, and REFUSE a row naming a different org;
* ``update`` REFUSES a payload that names a different org (an org column is never re-homed);
* declared foreign keys (``foreign_keys={"leads": {"stage_id": "lead_stages"}}``) are checked on every write: a
  non-null value must name a row of the SAME org in the parent table, else :class:`ForeignReferenceError` (422).
  This closes the confused-deputy class (a request naming another tenant's ``stage_id`` / ``client_id`` /
  ``post_id``): a plain FK constraint accepts any existing id, whoever owns it;
* ``rpc`` / ``schema`` / ``auth`` / ``storage`` and any other attribute are NOT exposed (an RPC bypasses the scope).

It is a drop-in for the supabase client in a service that only calls ``.table(name)`` (the product code keeps its
own ``.eq("org_id", ...)`` as defence in depth; a duplicate filter is harmless).

Tests: ``seed/lib/backend/tests/api/test_org_scoped.py``. KB § PATTERNS/security/access-tiers.md.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional
from uuid import UUID

from fastapi import HTTPException

__all__ = ["ForeignReferenceError", "OrgScopeViolation", "OrgScopedClient", "OrgScopedTable"]


class OrgScopeViolation(ValueError):
    """A write named an org other than the one the client is bound to. A programming error, never user input."""


class ForeignReferenceError(HTTPException):
    """A write references a row that does not exist in the caller's org (another tenant's id, or none)."""

    def __init__(self, table: str, column: str, parent: str):
        super().__init__(status_code=422, detail=f"Referência inválida: {column} não encontrado.")
        self.table, self.column, self.parent = table, column, parent


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


class OrgScopedTable:
    """One ``table(name)`` call. Mirrors the PostgREST builder entry points, injecting the org scope."""

    def __init__(self, scoped: "OrgScopedClient", name: str):
        self._s = scoped
        self._name = name
        self._inner = scoped._inner.table(name)

    # -- reads / deletes -------------------------------------------------------------------------------------
    def select(self, *args: Any, **kwargs: Any):
        return self._inner.select(*args, **kwargs).eq(self._s._col, self._s.org_id)

    def delete(self, *args: Any, **kwargs: Any):
        return self._inner.delete(*args, **kwargs).eq(self._s._col, self._s.org_id)

    # -- writes ----------------------------------------------------------------------------------------------
    def insert(self, values: Any, *args: Any, **kwargs: Any):
        rows = self._stamp(values)
        self._check_refs(rows)
        return self._inner.insert(rows, *args, **kwargs)

    def upsert(self, values: Any, *args: Any, **kwargs: Any):
        rows = self._stamp(values)
        self._check_refs(rows)
        return self._inner.upsert(rows, *args, **kwargs)

    def update(self, values: Mapping[str, Any], *args: Any, **kwargs: Any):
        payload = dict(values)
        if self._s._col in payload and _norm(payload[self._s._col]) != _norm(self._s.org_id):
            raise OrgScopeViolation(f"{self._name}: update names another org")
        payload.pop(self._s._col, None)
        self._check_refs([payload])
        return self._inner.update(payload, *args, **kwargs).eq(self._s._col, self._s.org_id)

    # -- internals -------------------------------------------------------------------------------------------
    def _stamp(self, values: Any):
        many = isinstance(values, (list, tuple))
        out = []
        for row in (values if many else [values]):
            row = dict(row)
            given = row.get(self._s._col)
            if given is not None and _norm(given) != _norm(self._s.org_id):
                raise OrgScopeViolation(f"{self._name}: row names another org")
            row[self._s._col] = self._s.org_id
            out.append(row)
        return out if many else out[0]

    def _check_refs(self, rows: Any) -> None:
        fks = self._s._fks.get(self._name)
        if not fks:
            return
        for row in rows if isinstance(rows, list) else [rows]:
            for column, parent in fks.items():
                value = row.get(column)
                if value is None:
                    continue
                found = (
                    self._s._inner.table(parent).select("id").eq(self._s._col, self._s.org_id).eq("id", str(value)).limit(1).execute()
                )
                if not (found.data or []):
                    raise ForeignReferenceError(self._name, column, parent)


class OrgScopedClient:
    """A service-role client bound to one org. See the module docstring."""

    def __init__(
        self,
        client: Any,
        org_id: Any,
        *,
        org_column: str = "org_id",
        foreign_keys: Optional[Mapping[str, Mapping[str, str]]] = None,
    ):
        if client is None:
            raise ValueError("OrgScopedClient needs a client")
        try:
            self.org_id = str(UUID(str(org_id)))
        except (ValueError, TypeError) as exc:
            raise ValueError("OrgScopedClient needs a real org id from the authenticated context") from exc
        self._inner = client
        self._col = org_column
        self._fks = dict(foreign_keys or {})

    def table(self, name: str) -> OrgScopedTable:
        return OrgScopedTable(self, name)

    from_ = table

    def __getattr__(self, name: str) -> Any:  # rpc / schema / auth / storage are deliberately unreachable
        raise AttributeError(f"OrgScopedClient does not expose '{name}': it would bypass the org scope")
