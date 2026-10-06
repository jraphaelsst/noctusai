"""In-memory PostgREST double for the Instagram insights module tests.

Unlike the seed ``MockSupabaseClient`` (whose ``or_`` is match-all and whose
``order`` is a no-op), this double EVALUATES ordering, the keyset ``or_``
expression the media grid uses, and ``on_conflict`` upserts — the exact
behaviours the module's correctness rests on (ordering + cursor pagination +
idempotent daily snapshots). Test-only; never imported by app code.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any


def _norm(v: Any) -> Any:
    """Comparable form: ISO timestamps → aware datetimes, else as-is."""
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", v):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v
    return v


_OPS = {
    "eq": lambda a, b: a == b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
}


def _split_top(expr: str) -> list[str]:
    parts, depth, cur, quoted = [], 0, "", False
    for ch in expr:
        if ch == '"':
            quoted = not quoted
        if not quoted and ch == "(":
            depth += 1
        if not quoted and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quoted:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _compile(expr: str):
    """PostgREST logic-tree subset: ``a.op.v,and(b.op.v,c.op.v)`` (top = OR)."""
    def atom(term: str):
        term = term.strip()
        if term.startswith("and(") and term.endswith(")"):
            subs = [atom(t) for t in _split_top(term[4:-1])]
            return lambda row: all(f(row) for f in subs)
        if term.startswith("or(") and term.endswith(")"):
            subs = [atom(t) for t in _split_top(term[3:-1])]
            return lambda row: any(f(row) for f in subs)
        col, op, val = term.split(".", 2)
        val = val[1:-1] if val.startswith('"') and val.endswith('"') else val
        fn = _OPS[op]
        return lambda row: fn(_norm(row.get(col)), _norm(val))

    subs = [atom(t) for t in _split_top(expr)]
    return lambda row: any(f(row) for f in subs)


class _Query:
    def __init__(self, store: "FakeSupabase", table: str) -> None:
        self._store = store
        self._table = table
        self._mode = "select"
        self._preds: list = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._payload: Any = None
        self._on_conflict: str | None = None

    # builders
    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def upsert(self, payload, on_conflict: str = "id", **_k):
        self._mode, self._payload, self._on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def _pred(self, op, col, val):
        fn = _OPS[op]
        self._preds.append(lambda row: fn(_norm(row.get(col)), _norm(val)))
        return self

    def eq(self, col, val):
        return self._pred("eq", col, val)

    def lt(self, col, val):
        return self._pred("lt", col, val)

    def gte(self, col, val):
        return self._pred("gte", col, val)

    def lte(self, col, val):
        return self._pred("lte", col, val)

    def or_(self, expr: str):
        self._preds.append(_compile(expr))
        return self

    def order(self, col, desc: bool = False, **_k):
        self._orders.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    # execution
    def execute(self):
        self._store.calls.append((self._table, self._mode))
        rows = self._store.tables.setdefault(self._table, [])
        if self._mode == "upsert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            keys = [k.strip() for k in (self._on_conflict or "id").split(",")]
            written = []
            for item in payload:
                match = next(
                    (r for r in rows if all(str(r.get(k)) == str(item.get(k)) for k in keys)),
                    None,
                )
                if match is None:
                    new = {"id": str(uuid.uuid4()), **copy.deepcopy(item)}
                    rows.append(new)
                    written.append(new)
                else:
                    match.update(copy.deepcopy(item))
                    written.append(match)
            return SimpleNamespace(data=copy.deepcopy(written), count=None)
        matched = [r for r in rows if all(p(r) for p in self._preds)]
        if self._mode == "update":
            for r in matched:
                r.update(copy.deepcopy(self._payload))
            return SimpleNamespace(data=copy.deepcopy(matched), count=None)
        for col, desc in reversed(self._orders):
            matched.sort(key=lambda r: _norm(r.get(col)), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=copy.deepcopy(matched), count=len(matched))


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, str]] = []

    def schema(self, _name: str) -> "FakeSupabase":
        return self

    def table(self, name: str) -> _Query:
        return _Query(self, name)
