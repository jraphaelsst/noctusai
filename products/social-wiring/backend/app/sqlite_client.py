"""SQLite-backed development client with a small Supabase-like surface.

This adapter exists so Phase 5 can be developed locally without touching
Supabase. It intentionally implements only the query-builder methods this
product uses: schema/table/select/insert/upsert/update/delete plus simple
filters, ordering, limits, and the one cursor OR shape used by video_cache.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JSON_COLUMNS = {
    "credentials": {"scopes"},
    "upload_jobs": {"tags", "notify_recipients"},
    "video_cache": {"tags"},
}

BOOL_COLUMNS = {
    "notification_recipients": {"is_active"},
    "video_cache": {"uploaded_via_app"},
}


@dataclass
class SQLiteResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class SQLiteClient:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def schema(self, _schema: str) -> "SQLiteClient":
        return self

    def table(self, table_name: str) -> "SQLiteQuery":
        return SQLiteQuery(self.db_path, table_name)


class SQLiteQuery:
    def __init__(self, db_path: Path, table_name: str):
        self._db_path = db_path
        self._table = table_name
        self._operation = "select"
        self._select = "*"
        self._count_exact = False
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._or_clause: str | None = None
        self._on_conflict: list[str] = []

    def select(self, columns: str = "*", *, count: str | None = None) -> "SQLiteQuery":
        self._operation = "select"
        self._select = columns
        self._count_exact = count == "exact"
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "SQLiteQuery":
        self._operation = "insert"
        self._payload = payload
        return self

    def upsert(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
    ) -> "SQLiteQuery":
        self._operation = "upsert"
        self._payload = payload
        self._on_conflict = [p.strip() for p in (on_conflict or "").split(",") if p.strip()]
        return self

    def update(self, payload: dict[str, Any]) -> "SQLiteQuery":
        self._operation = "update"
        self._payload = payload
        return self

    def delete(self) -> "SQLiteQuery":
        self._operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> "SQLiteQuery":
        self._filters.append((column, "=", value))
        return self

    def lt(self, column: str, value: Any) -> "SQLiteQuery":
        self._filters.append((column, "<", value))
        return self

    def in_(self, column: str, values: list[Any]) -> "SQLiteQuery":
        self._filters.append((column, "in", values))
        return self

    def order(self, column: str, *, desc: bool = False) -> "SQLiteQuery":
        self._orders.append((column, desc))
        return self

    def limit(self, value: int) -> "SQLiteQuery":
        self._limit = value
        return self

    def or_(self, value: str) -> "SQLiteQuery":
        self._or_clause = value
        return self

    def execute(self) -> SQLiteResponse:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if self._operation == "select":
                return self._execute_select(conn)
            if self._operation == "insert":
                return self._execute_insert(conn, upsert=False)
            if self._operation == "upsert":
                return self._execute_insert(conn, upsert=True)
            if self._operation == "update":
                return self._execute_update(conn)
            if self._operation == "delete":
                return self._execute_delete(conn)
        raise RuntimeError(f"unknown sqlite operation: {self._operation}")

    def _execute_select(self, conn: sqlite3.Connection) -> SQLiteResponse:
        columns = _select_columns(self._select)
        where_sql, params = self._where_sql()
        order_sql = ""
        if self._orders:
            bits = [
                f"{column} {'DESC' if desc else 'ASC'}"
                for column, desc in self._orders
            ]
            order_sql = " ORDER BY " + ", ".join(bits)
        limit_sql = ""
        if self._limit is not None:
            limit_sql = " LIMIT ?"
            params.append(self._limit)

        count_value = None
        if self._count_exact:
            count_params = list(params)
            if self._limit is not None:
                count_params = count_params[:-1]
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM {self._table}{where_sql}",
                count_params,
            ).fetchone()
            count_value = int(row["count"]) if row else 0

        rows = conn.execute(
            f"SELECT {columns} FROM {self._table}{where_sql}{order_sql}{limit_sql}",
            params,
        ).fetchall()
        return SQLiteResponse([self._row_to_dict(row) for row in rows], count=count_value)

    def _execute_insert(self, conn: sqlite3.Connection, *, upsert: bool) -> SQLiteResponse:
        payloads = self._payload if isinstance(self._payload, list) else [self._payload]
        out: list[dict[str, Any]] = []
        for payload in payloads:
            row = self._prepare_payload(dict(payload or {}))
            columns = list(row.keys())
            placeholders = ", ".join("?" for _ in columns)
            values = [row[column] for column in columns]
            conflict_sql = ""
            if upsert and self._on_conflict:
                update_columns = [c for c in columns if c not in self._on_conflict]
                assignments = ", ".join(f"{c}=excluded.{c}" for c in update_columns)
                conflict_sql = (
                    f" ON CONFLICT({', '.join(self._on_conflict)}) "
                    f"DO UPDATE SET {assignments}"
                )
            conn.execute(
                f"INSERT INTO {self._table} ({', '.join(columns)}) "
                f"VALUES ({placeholders}){conflict_sql}",
                values,
            )
            out.append(self._lookup_inserted(conn, row))
        conn.commit()
        return SQLiteResponse(out)

    def _execute_update(self, conn: sqlite3.Connection) -> SQLiteResponse:
        payload = self._prepare_payload(dict(self._payload or {}), add_defaults=False)
        if not payload:
            return SQLiteResponse([])
        assignments = ", ".join(f"{column}=?" for column in payload)
        params = list(payload.values())
        where_sql, where_params = self._where_sql()
        conn.execute(
            f"UPDATE {self._table} SET {assignments}{where_sql}",
            params + where_params,
        )
        rows = conn.execute(
            f"SELECT * FROM {self._table}{where_sql}",
            where_params,
        ).fetchall()
        conn.commit()
        return SQLiteResponse([self._row_to_dict(row) for row in rows])

    def _execute_delete(self, conn: sqlite3.Connection) -> SQLiteResponse:
        where_sql, params = self._where_sql()
        rows = conn.execute(
            f"SELECT * FROM {self._table}{where_sql}",
            params,
        ).fetchall()
        conn.execute(f"DELETE FROM {self._table}{where_sql}", params)
        conn.commit()
        return SQLiteResponse([self._row_to_dict(row) for row in rows])

    def _lookup_inserted(self, conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
        if "id" in row:
            found = conn.execute(
                f"SELECT * FROM {self._table} WHERE id = ? LIMIT 1",
                [row["id"]],
            ).fetchone()
            if found:
                return self._row_to_dict(found)
        where = []
        params = []
        for column in self._on_conflict:
            where.append(f"{column} = ?")
            params.append(row[column])
        if where:
            found = conn.execute(
                f"SELECT * FROM {self._table} WHERE {' AND '.join(where)} LIMIT 1",
                params,
            ).fetchone()
            if found:
                return self._row_to_dict(found)
        return row

    def _where_sql(self) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, op, value in self._filters:
            if op == "in":
                values = list(value or [])
                if not values:
                    clauses.append("1 = 0")
                    continue
                clauses.append(f"{column} IN ({', '.join('?' for _ in values)})")
                params.extend(_to_db_value(self._table, column, v) for v in values)
            else:
                clauses.append(f"{column} {op} ?")
                params.append(_to_db_value(self._table, column, value))

        if self._or_clause:
            parsed = _parse_video_cursor_or(self._or_clause)
            if parsed is not None:
                ts, row_id = parsed
                clauses.append("(published_at < ? OR (published_at = ? AND id < ?))")
                params.extend([ts, ts, row_id])

        if not clauses:
            return "", []
        return " WHERE " + " AND ".join(clauses), params

    def _prepare_payload(
        self,
        payload: dict[str, Any],
        *,
        add_defaults: bool = True,
    ) -> dict[str, Any]:
        if add_defaults and not payload.get("id"):
            payload["id"] = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if add_defaults:
            if "created_at" in _table_columns(self._table) and not payload.get("created_at"):
                payload["created_at"] = now
            if "updated_at" in _table_columns(self._table) and not payload.get("updated_at"):
                payload["updated_at"] = now
        return {
            column: _to_db_value(self._table, column, value)
            for column, value in payload.items()
        }

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        for column in JSON_COLUMNS.get(self._table, set()):
            if out.get(column) in (None, ""):
                out[column] = []
            elif isinstance(out[column], str):
                out[column] = json.loads(out[column])
        for column in BOOL_COLUMNS.get(self._table, set()):
            if column in out and out[column] is not None:
                out[column] = bool(out[column])
        return out


def _select_columns(select: str) -> str:
    if select.strip() == "*":
        return "*"
    columns = [part.strip() for part in select.split(",") if part.strip()]
    return ", ".join(columns) if columns else "*"


def _to_db_value(table: str, column: str, value: Any) -> Any:
    if column in JSON_COLUMNS.get(table, set()):
        return json.dumps(value or [])
    if column in BOOL_COLUMNS.get(table, set()) and value is not None:
        return 1 if value else 0
    # Generic fallback: supabase-py serialises dict/list for JSONB columns
    # automatically, but SQLite needs TEXT.  Any dict or list that reaches
    # here was NOT in the explicit JSON_COLUMNS allowlist, which means the
    # column is a JSONB column on the Postgres side (e.g. metadata,
    # channel_info on integration_accounts).  Serialise to JSON string so
    # the dev SQLite store accepts the value.
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _parse_video_cursor_or(value: str) -> tuple[str, str] | None:
    prefix = "published_at.lt."
    mid = ",and(published_at.eq."
    suffix = ",id.lt."
    if not value.startswith(prefix) or mid not in value or suffix not in value:
        return None
    ts = value[len(prefix): value.index(mid)]
    tail = value[value.index(suffix) + len(suffix):]
    row_id = tail[:-1] if tail.endswith(")") else tail
    return ts, row_id


def _table_columns(table: str) -> set[str]:
    return {
        "status_pagina": {"id", "nome_pagina", "status", "descricao", "created_at"},
        "invitations": {"id", "org_id", "email", "role", "invited_by", "token", "status", "expires_at", "created_at"},
        "credentials": {"id", "org_id", "provider", "encrypted_tokens", "channel_id", "channel_title", "scopes", "created_at", "updated_at"},
        "upload_jobs": {"id", "org_id", "youtube_video_id", "title", "description", "tags", "privacy_status", "category_id", "source_type", "source_url", "file_name", "file_size_bytes", "status", "progress_percent", "error_message", "notify_recipients", "created_by", "product_code", "thumbnail_url", "created_at", "updated_at"},
        "video_cache": {"id", "org_id", "youtube_video_id", "title", "description", "thumbnail_url", "published_at", "duration", "privacy_status", "view_count", "like_count", "comment_count", "favorite_count", "tags", "category_id", "uploaded_via_app", "synced_at"},
        "notification_recipients": {"id", "org_id", "name", "email", "whatsapp_number", "is_active", "created_at", "updated_at"},
        "notification_log": {"id", "org_id", "upload_job_id", "recipient_id", "channel", "status", "error_message", "sent_at", "created_at"},
        "whatsapp_connections": {"id", "org_id", "user_id", "label", "base_url", "session_name", "encrypted_api_key", "webhook_url", "created_at", "updated_at"},
    }.get(table, set())
