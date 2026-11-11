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
* ``upsert`` is refused unless its ``on_conflict`` names the org column (or ``ignore_duplicates=True``), and
  ``insert(..., upsert=True)`` is refused: ``ON CONFLICT (id) DO UPDATE SET org_id=<mine>`` would MOVE another tenant's
  row into the caller's org. The conflict target must be a composite unique key that includes the org column;
* ``select`` column strings may not carry an embed / alias / cast (``(``, ``!``, ``:``): an embedded relation is not
  filtered by the parent's org predicate;
* ``reference_validators`` (``{table: {column: fn(ids) -> valid_ids}}``) prove ids that live outside the schema (a user id
  that must belong to the org) with the same 422 as a foreign key. Both checks are batched: ONE query per distinct
  (column, parent) per write, however many rows;
* ``rpc`` / ``schema`` / ``auth`` / ``storage`` and any other attribute are NOT exposed (an RPC bypasses the scope), and the
  wrapped client itself is name-mangled (``test_service_only_lockdown`` bans reaching for it).

It is a drop-in for the supabase client in a service that only calls ``.table(name)`` (the product code keeps its
own ``.eq("org_id", ...)`` as defence in depth; a duplicate filter is harmless).

Tests: ``seed/lib/backend/tests/api/test_org_scoped.py``. KB § PATTERNS/security/access-tiers.md.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional
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


_EMBED_CHARS = ("(", "!", ":")
_IN_BATCH = 100


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


class OrgScopedTable:
    """One ``table(name)`` call. Mirrors the PostgREST builder entry points, injecting the org scope."""

    def __init__(self, scoped: "OrgScopedClient", name: str):
        self._s = scoped
        self._name = name
        self.__builder = _raw(scoped, name)

    # -- reads / deletes -------------------------------------------------------------------------------------
    def select(self, *args: Any, **kwargs: Any):
        # postgrest-py joins EVERY positional column argument: judge them all (and the keyword form), not just the first.
        cols = ",".join(str(c) for c in (*args, *([kwargs["columns"]] if "columns" in kwargs else []))) or "*"
        if any(ch in cols for ch in _EMBED_CHARS):
            raise OrgScopeViolation(f"{self._name}: select(...) may not embed, alias or cast ({cols!r}): embeds are not org-filtered")
        return self.__builder.select(*args, **kwargs).eq(self._s._col, self._s.org_id)

    def delete(self, *args: Any, **kwargs: Any):
        return self.__builder.delete(*args, **kwargs).eq(self._s._col, self._s.org_id)

    # -- writes ----------------------------------------------------------------------------------------------
    def insert(self, values: Any, *args: Any, **kwargs: Any):
        if kwargs.get("upsert"):
            raise OrgScopeViolation(f"{self._name}: insert(upsert=True) is refused; use upsert(on_conflict='{self._s._col},...')")
        rows = self._stamp(values)
        self._check_refs(rows)
        return self.__builder.insert(rows, *args, **kwargs)

    def upsert(self, values: Any, *args: Any, **kwargs: Any):
        conflict = kwargs.get("on_conflict") or (args[0] if args and isinstance(args[0], str) else "")
        keys = {k.strip() for k in str(conflict).split(",") if k.strip()}
        # `ignore_duplicates=True` is no way round it: DO NOTHING on a global key is an existence oracle (the row count tells
        # whether another tenant holds the key) and lets one tenant block another's insert. An EXPLICIT on_conflict must name the
        # org; with neither given, ignore_duplicates alone (the default arbiter is the primary key) is refused the same way.
        if self._s._col not in keys:
            raise OrgScopeViolation(
                f"{self._name}: upsert needs on_conflict naming '{self._s._col}' (a composite unique key), also with "
                "ignore_duplicates=True: a conflict on a global key would move, block or reveal another tenant's row")
        rows = self._stamp(values)
        self._check_refs(rows)
        return self.__builder.upsert(rows, *args, **kwargs)

    def update(self, values: Mapping[str, Any], *args: Any, **kwargs: Any):
        payload = dict(values)
        if self._s._col in payload and _norm(payload[self._s._col]) != _norm(self._s.org_id):
            raise OrgScopeViolation(f"{self._name}: update names another org")
        payload.pop(self._s._col, None)
        self._check_refs([payload])
        return self.__builder.update(payload, *args, **kwargs).eq(self._s._col, self._s.org_id)

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
        fks = self._s._fks.get(self._name) or {}
        validators = self._s._validators.get(self._name) or {}
        if not fks and not validators:
            return
        rows = rows if isinstance(rows, list) else [rows]
        for column, parent in fks.items():
            wanted = _distinct(rows, column)
            if not wanted:
                continue
            found: set[str] = set()
            for chunk in _chunks(sorted(wanted)):
                res = _raw(self._s, parent).select("id").eq(self._s._col, self._s.org_id).in_("id", chunk).execute()
                found |= {_norm(r.get("id")) for r in (res.data or [])}
            if wanted - found:
                raise ForeignReferenceError(self._name, column, parent)
        for column, validate in validators.items():
            wanted = _distinct(rows, column)
            if wanted and wanted - {_norm(v) for v in validate(set(wanted))}:
                raise ForeignReferenceError(self._name, column, "validator")


def _distinct(rows: Iterable[Mapping[str, Any]], column: str) -> set[str]:
    return {_norm(r[column]) for r in rows if r.get(column) is not None}


def _chunks(values: list[str]):
    for i in range(0, len(values), _IN_BATCH):
        yield values[i: i + _IN_BATCH]


def _raw(scoped: "OrgScopedClient", name: str):
    """The ONLY place that touches the wrapped client (name-mangled). The lockdown test bans every other reference."""
    return scoped._OrgScopedClient__inner.table(name)


class OrgScopedClient:
    """A service-role client bound to one org. See the module docstring."""

    def __init__(
        self,
        client: Any,
        org_id: Any,
        *,
        org_column: str = "org_id",
        foreign_keys: Optional[Mapping[str, Mapping[str, str]]] = None,
        reference_validators: Optional[Mapping[str, Mapping[str, Callable[[set[str]], Iterable[Any]]]]] = None,
    ):
        if client is None:
            raise ValueError("OrgScopedClient needs a client")
        try:
            self.org_id = str(UUID(str(org_id)))
        except (ValueError, TypeError) as exc:
            raise ValueError("OrgScopedClient needs a real org id from the authenticated context") from exc
        self.__inner = client
        self._col = org_column
        self._fks = dict(foreign_keys or {})
        self._validators = dict(reference_validators or {})

    def table(self, name: str) -> OrgScopedTable:
        return OrgScopedTable(self, name)

    from_ = table

    def __getattr__(self, name: str) -> Any:  # rpc / schema / auth / storage are deliberately unreachable
        raise AttributeError(f"OrgScopedClient does not expose '{name}': it would bypass the org scope")
