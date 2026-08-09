"""SQLite :class:`~.types.RecordStore` — the local-development backend.

Why SQLite is a *real* adapter and not a second Fake: it exercises real
SQL, real constraints, real transactions and real type affinity, so a
product built against it is exercising a genuine database rather than a
dict. The Fake stays for unit tests; this runs the app.

**Tenant isolation.** SQLite has no RLS. Every statement this adapter
emits carries an ``org_id = ?`` predicate, injected here rather than
left to callers — the app-layer substitute for the row-level policies
the Postgres path will enforce. This is the accepted divergence recorded
in ``KB § PATTERNS/common/accept-with-rationale.md``; the migrations
still ship the real ``CREATE POLICY`` statements so isolation becomes
db-enforced the moment the product lands on Postgres.

**Identifier safety.** Table and column names cannot be parameterised in
SQL, so every identifier reaching a statement is validated against
:func:`_ident` (strict allowlist) and quoted. Values are ALWAYS bound
parameters — never interpolated.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import Op, PersistenceError, QuerySpec, Record, RecordNotFound, RecordStore

__all__ = ["SqliteRecordStore"]

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_OP_SQL: dict[Op, str] = {
    Op.EQ: "=",
    Op.NEQ: "!=",
    Op.LT: "<",
    Op.LTE: "<=",
    Op.GT: ">",
    Op.GTE: ">=",
}


def _ident(name: str) -> str:
    """Validate + quote a SQL identifier.

    Raises on anything outside ``[A-Za-z_][A-Za-z0-9_]*``. This is the
    injection boundary: identifiers are the one thing that cannot be a
    bound parameter, so they get an allowlist instead of escaping.
    """
    if not _IDENT_RE.match(name):
        raise PersistenceError(f"unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def _encode(value: Any) -> Any:
    """Adapt a Python value to something sqlite3 can bind.

    dict/list round-trip as JSON text — the SQLite stand-in for the
    ``jsonb`` columns the Postgres schema uses (brand palettes, persona
    payloads, metric snapshots). :func:`_decode` reverses it.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decode(value: Any) -> Any:
    """Best-effort reverse of :func:`_encode` for JSON-shaped text."""
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class SqliteRecordStore:
    """A :class:`~.types.RecordStore` backed by a SQLite file (or ``:memory:``).

    Thread-safety: FastAPI runs handlers across a threadpool, so the
    connection is created with ``check_same_thread=False`` and every
    statement is serialised behind an :class:`threading.RLock`. SQLite's
    own locking would otherwise surface as sporadic
    ``database is locked`` errors under concurrent requests — a flake
    class that is miserable to debug in production and trivial to
    prevent here.
    """

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._database = str(database)
        if self._database != ":memory:":
            Path(self._database).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._database, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL keeps readers from blocking the writer — the right default
        # for an API server. Foreign keys are OFF by default in SQLite,
        # which would silently accept orphaned rows the Postgres schema
        # rejects; turning them on keeps the two backends honest.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # ── lifecycle ───────────────────────────────────────────────────
    @property
    def connection(self) -> sqlite3.Connection:
        """The live connection — for migrations and product-owned SQL."""
        return self._conn

    def executescript(self, script: str) -> None:
        """Run a multi-statement SQL script (migration application)."""
        with self._lock:
            self._conn.executescript(script)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── query construction ──────────────────────────────────────────
    def _where(self, org_id: str, spec: QuerySpec) -> tuple[str, list[Any]]:
        """Build the WHERE clause. ``org_id`` is always the first term."""
        clauses = [f"{_ident('org_id')} = ?"]
        params: list[Any] = [org_id]
        for f in spec.filters:
            col = _ident(f.column)
            if f.op is Op.IS_NULL:
                clauses.append(f"{col} IS {'NULL' if f.value else 'NOT NULL'}")
            elif f.op is Op.IN:
                values = list(f.value)
                if not values:
                    # `IN ()` is a syntax error in SQLite and an empty set
                    # matches nothing — encode that directly.
                    clauses.append("0 = 1")
                    continue
                clauses.append(f"{col} IN ({','.join('?' * len(values))})")
                params.extend(_encode(v) for v in values)
            elif f.op is Op.CONTAINS:
                # LIKE is case-insensitive for ASCII in SQLite by default;
                # LOWER() on both sides makes it explicit and unicode-safer.
                clauses.append(f"LOWER({col}) LIKE ?")
                params.append(f"%{str(f.value).lower()}%")
            else:
                clauses.append(f"{col} {_OP_SQL[f.op]} ?")
                params.append(_encode(f.value))
        return " AND ".join(clauses), params

    def _tail(self, spec: QuerySpec) -> str:
        sql = ""
        if spec.order_by:
            parts = [
                f"{_ident(o.column)} {'DESC' if o.descending else 'ASC'}"
                for o in spec.order_by
            ]
            sql += " ORDER BY " + ", ".join(parts)
        if spec.limit is not None:
            sql += f" LIMIT {int(spec.limit)}"
            if spec.offset:
                sql += f" OFFSET {int(spec.offset)}"
        elif spec.offset:
            # SQLite requires a LIMIT before OFFSET; -1 means "no limit".
            sql += f" LIMIT -1 OFFSET {int(spec.offset)}"
        return sql

    @staticmethod
    def _row(row: sqlite3.Row) -> Record:
        return {k: _decode(row[k]) for k in row.keys()}

    # ── RecordStore ─────────────────────────────────────────────────
    def insert(self, table: str, org_id: str, values: Record) -> Record:
        payload = dict(values)
        payload["org_id"] = org_id
        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        cols = [_ident(k) for k in payload]
        placeholders = ",".join("?" * len(payload))
        sql = f"INSERT INTO {_ident(table)} ({','.join(cols)}) VALUES ({placeholders})"
        with self._lock:
            try:
                self._conn.execute(sql, [_encode(v) for v in payload.values()])
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                raise PersistenceError(f"insert into {table} violated a constraint: {exc}") from exc
        return self.get(table, org_id, str(payload["id"]))

    def get(self, table: str, org_id: str, record_id: str) -> Record:
        sql = f"SELECT * FROM {_ident(table)} WHERE {_ident('id')} = ? AND {_ident('org_id')} = ?"
        with self._lock:
            row = self._conn.execute(sql, [record_id, org_id]).fetchone()
        if row is None:
            raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        return self._row(row)

    def list(self, table: str, org_id: str, spec: QuerySpec | None = None) -> list[Record]:
        spec = spec or QuerySpec()
        cols = ",".join(_ident(c) for c in spec.columns) if spec.columns else "*"
        where, params = self._where(org_id, spec)
        sql = f"SELECT {cols} FROM {_ident(table)} WHERE {where}{self._tail(spec)}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def update(self, table: str, org_id: str, record_id: str, values: Record) -> Record:
        patch = {k: v for k, v in values.items() if k not in {"id", "org_id"}}
        if not patch:
            # Nothing to write, but the caller still expects the row (and
            # a RecordNotFound if it is absent) — delegate to get().
            return self.get(table, org_id, record_id)
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ",".join(f"{_ident(k)} = ?" for k in patch)
        sql = (
            f"UPDATE {_ident(table)} SET {assignments} "
            f"WHERE {_ident('id')} = ? AND {_ident('org_id')} = ?"
        )
        params = [_encode(v) for v in patch.values()] + [record_id, org_id]
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            if cur.rowcount == 0:
                raise RecordNotFound(f"{table}:{record_id} not found in org {org_id}")
        return self.get(table, org_id, record_id)

    def delete(self, table: str, org_id: str, record_id: str) -> bool:
        sql = f"DELETE FROM {_ident(table)} WHERE {_ident('id')} = ? AND {_ident('org_id')} = ?"
        with self._lock:
            cur = self._conn.execute(sql, [record_id, org_id])
            self._conn.commit()
            return cur.rowcount > 0

    def count(self, table: str, org_id: str, spec: QuerySpec | None = None) -> int:
        spec = spec or QuerySpec()
        where, params = self._where(org_id, spec)
        sql = f"SELECT COUNT(*) AS n FROM {_ident(table)} WHERE {where}"
        with self._lock:
            return int(self._conn.execute(sql, params).fetchone()["n"])

