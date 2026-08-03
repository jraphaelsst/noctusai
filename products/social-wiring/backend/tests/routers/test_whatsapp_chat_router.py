"""Tests for per-connection chat endpoints.

Drives every endpoint through DI seams — same Class-B pattern as
``test_whatsapp_connections_router.py``:

  - ``get_connection_store``             → SQLite-backed WhatsAppConnectionStore
  - ``get_message_store_factory``        → factory returning SQLite-backed MessageStore
  - ``get_chat_store_factory``           → factory returning SQLite-backed WhatsAppChatStore
  - ``get_chat_messages_reader_factory`` → factory returning SQLite-backed _ChatMessagesReader
  - ``get_waha_client_factory``          → per-session FakeWahaClient producer

Auth is exercised via the shared ``client`` fixture (MockSupabaseClient).  No
external calls; FakeWahaClient drives the send / recover / read-receipt paths.

Endpoints under test
--------------------
  GET  /api/whatsapp/connections/{id}/chats                    (pure Postgres, Slice 5)
  GET  /api/whatsapp/connections/{id}/chats/{chat_id:path}/messages (pure Postgres, Slice 5)
  POST /api/whatsapp/connections/{id}/chats/{chat_id:path}/read      (Slice 5, new)
  POST /api/whatsapp/connections/{id}/chats/{chat_id:path}/send
  POST /api/whatsapp/connections/{id}/recover                        (Slice 5, new)
  GET  /api/whatsapp/connections/{id}/stream                         (Slice 5, new — SSE)
  PUT  /api/whatsapp/connections/{id}/auto-reply

Contract pins
-------------
  - 401 on unauthenticated access (assert strict `== 401`, never `in (401, 404)`).
  - 404 for a connection owned by a DIFFERENT user_id (ownership guard).
  - 422 on empty ``text`` in send (Pydantic min_length=1).
  - 201 on send + outbound row tagged with connection_id.
  - 502 on WAHA send / recover failure.
  - GET /chats and GET /chats/{id}/messages return the keyset envelope
    ``{items, next_before}`` — WAHA is NEVER called on either read path
    (Slice 5 deleted the WAHA-merge code entirely; see
    ``TestNoWahaOnReadPath``).
  - POST .../read zeroes unread_count, publishes chat.read, and returns
    before ``send_seen`` (background, never awaited).
  - auto_reply_enabled surfaces in GET /connections response (False by default).
  - PUT /auto-reply toggles the flag + 404 for wrong owner.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.whatsapp import FakeWahaClient

from app.services.message_store import MessageStore, StoredMessage
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import WhatsAppConnectionStore
from app.sqlite_client import SQLiteClient

# ── Shared constants ─────────────────────────────────────────────────────────

_PRODUCT_BASE = "https://social.noctusai.com"

# UUID derived by coerce_org_uuid("test-org-123") = uuid5(NAMESPACE_OID, "test-org-123")
# Computed via: from uuid import uuid5, NAMESPACE_OID; uuid5(NAMESPACE_OID, "test-org-123")
_TEST_ORG_ID = "48ab962b-ec86-517e-9e42-7b581f622377"

_CONN_SCHEMA = """
CREATE TABLE whatsapp_connections (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT,
    auto_reply_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, user_id, label),
    UNIQUE (webhook_token)
);
"""

# Migration 040 columns: ack / acked_at / chat_id.
_MSG_SCHEMA = """
CREATE TABLE conversation_messages (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    raw_sender TEXT,
    direction TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    provider_message_id TEXT UNIQUE,
    authorized INTEGER NOT NULL DEFAULT 1,
    structured_payload TEXT,
    connection_id TEXT,
    ack INTEGER,
    acked_at TEXT,
    chat_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

# Migration 040 — social_wiring.whatsapp_chats.
_CHATS_SCHEMA = """
CREATE TABLE whatsapp_chats (
    connection_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    title TEXT,
    last_message_at TEXT,
    last_message_preview TEXT,
    last_direction TEXT,
    unread_count INTEGER NOT NULL DEFAULT 0,
    last_read_at TEXT,
    last_read_message_id TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    synced_through TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (connection_id, chat_id)
);
"""

# ── SQLite-backed MessageStore (mirrors production Supabase client interface) ─

class _SQLiteSchemaClient:
    """Minimal Supabase-like client backed by SQLite for test isolation."""

    def __init__(self, db_path: Path):
        self._db_path = db_path

    def schema(self, name: str) -> "_SQLiteSchemaProxy":
        return _SQLiteSchemaProxy(self._db_path)


class _SQLiteSchemaProxy:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def table(self, name: str) -> "_SQLiteTableProxy":
        return _SQLiteTableProxy(self._db_path, name)


class _SQLiteTableProxy:
    """Minimal query builder — enough to support the MessageStore /
    WhatsAppChatStore / _ChatMessagesReader interfaces (select/eq/lt/order/
    limit/update/execute — real SQL ORDER BY + LIMIT, unlike
    ``noctusai_lib.testing.MockSupabaseClient`` which no-ops both, so
    keyset-pagination logic is exercised end-to-end here)."""

    def __init__(self, db_path: Path, table: str):
        self._db_path = db_path
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._order_col: str | None = None
        self._order_desc: bool = False
        self._limit_n: int | None = None
        self._select_cols: str = "*"
        self._lt_col: str | None = None
        self._lt_val: Any = None

    # ── chainable query-builder methods ──────────────────────────────────

    def select(self, cols: str, *, count: str | None = None) -> "_SQLiteTableProxy":
        # `count="exact"` mirrors PostgREST returning the row count out-of-band
        # on `response.count`. WhatsAppChatStore._recount_unread relies on it,
        # so the fake must surface it too — falling back to len(data) here
        # would hide a real "driver did not supply a count" case.
        self._select_cols = cols
        self._count_mode = count
        return self

    def eq(self, col: str, val: Any) -> "_SQLiteTableProxy":
        self._filters.append(("=", col, val))
        return self

    def lt(self, col: str, val: Any) -> "_SQLiteTableProxy":
        self._lt_col = col
        self._lt_val = val
        return self

    def order(self, col: str, *, desc: bool = False) -> "_SQLiteTableProxy":
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_SQLiteTableProxy":
        self._limit_n = n
        return self

    def insert(self, payload: dict) -> "_SQLiteTableProxy":
        cols = ", ".join(f'"{k}"' for k in payload)
        placeholders = ", ".join("?" for _ in payload)
        vals = list(payload.values())
        sql = f'INSERT INTO "{self._table}" ({cols}) VALUES ({placeholders})'
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(sql, vals)
        # Return proxy for execute() to re-read the inserted row.
        self._filters = [("=", "id", payload["id"])]
        self._select_cols = "*"
        return self

    def upsert(self, payload: dict, *, on_conflict: str = "") -> "_SQLiteTableProxy":
        """Real INSERT .. ON CONFLICT DO UPDATE, mirroring Supabase's upsert.

        Implemented against actual SQL rather than stubbed because
        ``WhatsAppChatStore.record_message`` relies on upsert semantics for its
        idempotency guarantee — a fake that merely inserted would let a
        replayed webhook raise instead of converging, and the test would be
        proving the opposite of the production behaviour.
        """
        cols = ", ".join(f'"{k}"' for k in payload)
        placeholders = ", ".join("?" for _ in payload)
        vals = list(payload.values())
        conflict_cols = [c.strip() for c in on_conflict.split(",") if c.strip()]
        sql = f'INSERT INTO "{self._table}" ({cols}) VALUES ({placeholders})'
        if conflict_cols:
            targets = ", ".join(f'"{c}"' for c in conflict_cols)
            updates = ", ".join(
                f'"{k}" = excluded."{k}"' for k in payload if k not in conflict_cols
            )
            sql += (
                f" ON CONFLICT({targets}) DO UPDATE SET {updates}"
                if updates
                else f" ON CONFLICT({targets}) DO NOTHING"
            )
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(sql, vals)
        self._filters = [("=", c, payload[c]) for c in conflict_cols if c in payload]
        self._select_cols = "*"
        return self

    def update(self, patch: dict) -> "_SQLiteTableProxy":
        set_clauses = ", ".join(f'"{k}" = ?' for k in patch)
        self._pending_update = (set_clauses, list(patch.values()))
        return self

    # ── terminal method ───────────────────────────────────────────────────

    def execute(self) -> Any:
        if hasattr(self, "_pending_update"):
            # UPDATE path: apply update then re-read.
            set_clauses, set_vals = self._pending_update
            where_clauses: list[str] = []
            where_vals: list[Any] = []
            for op, col, val in self._filters:
                where_clauses.append(f'"{col}" {op} ?')
                where_vals.append(val)
            if self._lt_col:
                where_clauses.append(f'"{self._lt_col}" < ?')
                where_vals.append(self._lt_val)
            where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            sql_up = f'UPDATE "{self._table}" SET {set_clauses} {where}'
            sql_sel = f'SELECT * FROM "{self._table}" {where}'
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute(sql_up, set_vals + where_vals)
                rows = conn.execute(sql_sel, where_vals).fetchall()
            return _Response([dict(r) for r in rows])

        # SELECT path (default).
        where_clauses: list[str] = []
        params: list[Any] = []
        for op, col, val in self._filters:
            where_clauses.append(f'"{col}" {op} ?')
            params.append(val)
        if self._lt_col:
            where_clauses.append(f'"{self._lt_col}" < ?')
            params.append(self._lt_val)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if self._select_cols == "*":
            cols_sql = "*"
        else:
            cols_sql = ", ".join(
                f'"{c.strip()}"' for c in self._select_cols.split(",")
            )

        order = ""
        if self._order_col:
            direction = "DESC" if self._order_desc else "ASC"
            order = f'ORDER BY "{self._order_col}" {direction}'

        limit = f"LIMIT {self._limit_n}" if self._limit_n is not None else ""
        sql = f'SELECT {cols_sql} FROM "{self._table}" {where} {order} {limit}'

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            exact_count: int | None = None
            if getattr(self, "_count_mode", None) == "exact":
                count_sql = f'SELECT COUNT(*) AS n FROM "{self._table}" {where}'
                exact_count = conn.execute(count_sql, params).fetchone()["n"]
        return _Response([dict(r) for r in rows], count=exact_count)


class _Response:
    def __init__(self, data: list[dict], *, count: int | None = None):
        self.data = data
        # PostgREST exposes the exact row count out-of-band when the caller
        # asked for it; None otherwise. Mirrored so a consumer that branches on
        # "did the driver give me a count?" is exercised faithfully.
        self.count = count


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def chat_client(client, tmp_path: Path, override_settings, monkeypatch):
    """Full DI-wired client for the chat endpoints.

    Sets up:
      - SQLite-backed WhatsAppConnectionStore (conn table + msg table + chats table)
      - SQLite-backed MessageStore factory
      - SQLite-backed WhatsAppChatStore factory
      - SQLite-backed _ChatMessagesReader factory
      - FakeWahaClient for the send / recover / read-receipt paths
      - waha_base_url + PRODUCT_URL_SOCIAL_WIRING env
    """
    from app.main import app
    from app.routers.whatsapp_connections_router import (
        _ChatMessagesReader,
        get_chat_messages_reader_factory,
        get_chat_store_factory,
        get_connection_store,
        get_message_store_factory,
        get_waha_client_factory,
    )

    override_settings(waha_base_url="https://waha.example.com")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", _PRODUCT_BASE)

    # Shared db_path used by every store so cross-table reads see the same data.
    db_path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_CONN_SCHEMA + _MSG_SCHEMA + _CHATS_SCHEMA)

    conn_store = WhatsAppConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(Fernet.generate_key())
    )
    schema_client = _SQLiteSchemaClient(db_path)

    def _make_msg_store(org_id: UUID) -> MessageStore:
        return MessageStore(admin_supabase=schema_client, org_id=org_id)

    def _make_chat_store(org_id: UUID) -> WhatsAppChatStore:
        return WhatsAppChatStore(admin_supabase=schema_client, org_id=org_id)

    def _make_chat_messages_reader(org_id: UUID) -> _ChatMessagesReader:
        return _ChatMessagesReader(admin_supabase=schema_client, org_id=org_id)

    fakes: dict[str, FakeWahaClient] = {}

    def _fake_factory(*, base_url=None, api_key=None, session="default"):
        return fakes.setdefault(session, FakeWahaClient(session=session))

    overrides = {
        get_connection_store: lambda: conn_store,
        get_message_store_factory: lambda: _make_msg_store,
        get_chat_store_factory: lambda: _make_chat_store,
        get_chat_messages_reader_factory: lambda: _make_chat_messages_reader,
        get_waha_client_factory: lambda: _fake_factory,
    }
    _prev = {dep: app.dependency_overrides.get(dep) for dep in overrides}
    app.dependency_overrides.update(overrides)

    yield client, conn_store, fakes, db_path

    for dep, prev in _prev.items():
        if prev is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = prev


def _create_connection(c, *, label="Test Line", api_key="k") -> dict:
    resp = c.post("/api/whatsapp/connections", json={"label": label, "api_key": api_key})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_messages(db_path: Path, *, org_id: str, connection_id: str, rows: list[dict]) -> None:
    """Directly insert conversation_messages rows into SQLite for test setup."""
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            row.setdefault("id", str(uuid4()))
            row.setdefault("org_id", org_id)
            row.setdefault("session_id", "default")
            row.setdefault("connection_id", connection_id)
            row.setdefault("authorized", 1)
            row.setdefault("provider_message_id", None)
            row.setdefault("structured_payload", None)
            row.setdefault("ack", None)
            row.setdefault("acked_at", None)
            row.setdefault("chat_id", row.get("raw_sender"))
            row.setdefault("created_at", "2026-06-22T10:00:00.000Z")
            cols = ", ".join(f'"{k}"' for k in row)
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f'INSERT INTO conversation_messages ({cols}) VALUES ({placeholders})',
                list(row.values()),
            )


def _seed_chats(db_path: Path, *, org_id: str, connection_id: str, rows: list[dict]) -> None:
    """Directly insert whatsapp_chats rows into SQLite for test setup —
    mirrors what `WhatsAppChatStore.record_message` (the ingest write path,
    peer territory — not exercised here) would have produced."""
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            row.setdefault("org_id", org_id)
            row.setdefault("connection_id", connection_id)
            row.setdefault("title", None)
            row.setdefault("last_message_at", None)
            row.setdefault("last_message_preview", "")
            row.setdefault("last_direction", None)
            row.setdefault("unread_count", 0)
            row.setdefault("last_read_at", None)
            row.setdefault("last_read_message_id", None)
            row.setdefault("archived", 0)
            row.setdefault("pinned", 0)
            cols = ", ".join(f'"{k}"' for k in row)
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f'INSERT INTO whatsapp_chats ({cols}) VALUES ({placeholders})',
                list(row.values()),
            )


# ── GET /chats — pure Postgres, keyset envelope (Slice 5) ────────────────────

class TestListChats:
    def test_empty_returns_envelope_with_empty_items(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        resp = c.get(f"/api/whatsapp/connections/{created['id']}/chats")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"items": [], "next_before": None}

    def test_401_unauthenticated(self, chat_client):
        """No Authorization header → 401 strictly (not 503 / 404)."""
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.get(f"/api/whatsapp/connections/{uuid4()}/chats")
        assert resp.status_code == 401, resp.text

    def test_404_other_user_connection(self, chat_client):
        """A connection owned by a different user_id is opaque → 404."""
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org,
            user_id=other_user,
            label="Other",
            base_url="https://waha.example.com",
            api_key="other-key",
        )
        resp = c.get(f"/api/whatsapp/connections/{other_conn.id}/chats")
        assert resp.status_code == 404, resp.text

    def test_orders_by_last_message_at_desc(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "title": "5511", "last_message_at": "2026-06-22T09:00:00.000Z",
             "last_message_preview": "hi", "last_direction": "inbound"},
            {"chat_id": "5522@c.us", "title": "5522", "last_message_at": "2026-06-22T10:01:00.000Z",
             "last_message_preview": "hey", "last_direction": "outbound"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["chat_id"] == "5522@c.us"
        assert items[0]["last_direction"] == "outbound"
        assert items[1]["chat_id"] == "5511@c.us"

    def test_chat_dto_shape(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511999998888@c.us", "title": "Ana",
             "last_message_at": "2026-06-22T10:00:00.000Z",
             "last_message_preview": "oi", "last_direction": "inbound",
             "unread_count": 2},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        for field in (
            "chat_id", "title", "last_message_at", "last_message_preview",
            "last_direction", "unread_count", "last_read_at", "archived", "pinned",
        ):
            assert field in item, f"Missing ChatDTO field: {field}"
        assert item["title"] == "Ana"
        assert item["unread_count"] == 2
        # The old WAHA-merge era ChatSummary fields must NOT be present.
        assert "contact" not in item
        assert "last_message" not in item
        assert "unread" not in item

    def test_archived_default_false_excludes_archived_chats(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z",
             "last_message_preview": "active", "archived": 0},
            {"chat_id": "5522@c.us", "last_message_at": "2026-06-22T10:00:00.000Z",
             "last_message_preview": "archived one", "archived": 1},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert [i["chat_id"] for i in items] == ["5511@c.us"]

    def test_next_before_set_on_full_page(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z", "last_message_preview": "a"},
            {"chat_id": "5522@c.us", "last_message_at": "2026-06-22T10:00:00.000Z", "last_message_preview": "b"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats", params={"limit": 1})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["chat_id"] == "5522@c.us"  # newest first
        assert body["next_before"] == "2026-06-22T10:00:00.000Z"

    def test_next_before_null_when_page_not_full(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z", "last_message_preview": "a"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats", params={"limit": 30})
        assert resp.status_code == 200, resp.text
        assert resp.json()["next_before"] is None

    def test_before_cursor_pages_toward_older_history(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z", "last_message_preview": "older"},
            {"chat_id": "5522@c.us", "last_message_at": "2026-06-22T10:00:00.000Z", "last_message_preview": "newer"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats",
            params={"before": "2026-06-22T10:00:00.000Z"},
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert [i["chat_id"] for i in items] == ["5511@c.us"]


# ── GET /chats/{chat_id}/messages — pure Postgres, keyset envelope (Slice 5) ─

class TestListMessages:
    def test_empty_thread_returns_envelope_with_empty_items(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        resp = c.get(
            f"/api/whatsapp/connections/{created['id']}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": [], "next_before": None}

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.get(f"/api/whatsapp/connections/{uuid4()}/chats/5511@c.us/messages")
        assert resp.status_code == 401, resp.text

    def test_404_other_user_connection(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="Other2", base_url="https://waha.example.com", api_key="k2",
        )
        resp = c.get(
            f"/api/whatsapp/connections/{other_conn.id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 404, resp.text

    def test_returns_messages_newest_first(self, chat_client):
        """Newest-first per page — mirrors GET /chats's pagination shape;
        `next_before` is always the LAST item's cursor field in the page."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "first",
             "created_at": "2026-06-22T09:00:00.000Z"},
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "outbound", "body": "second",
             "created_at": "2026-06-22T09:01:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()["items"]
        assert len(msgs) == 2
        assert msgs[0]["body"] == "second"
        assert msgs[0]["direction"] == "outbound"
        assert msgs[1]["body"] == "first"
        assert msgs[1]["direction"] == "inbound"

    def test_before_cursor_filters_newer_messages(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "old",
             "created_at": "2026-06-22T08:00:00.000Z"},
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "newer",
             "created_at": "2026-06-22T09:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages",
            params={"before": "2026-06-22T08:30:00.000Z"},
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()["items"]
        assert len(msgs) == 1
        assert msgs[0]["body"] == "old"

    def test_message_dto_shape_includes_ack_fields(self, chat_client):
        """Verify all required MessageDTO fields are in the response,
        including the migration-040 ack/acked_at columns."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "outbound", "body": "check",
             "created_at": "2026-06-22T10:00:00.000Z", "ack": 2,
             "acked_at": "2026-06-22T10:00:05.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msg = resp.json()["items"][0]
        for field in (
            "id", "provider_message_id", "chat_id", "direction", "body",
            "ack", "acked_at", "created_at", "structured_payload",
        ):
            assert field in msg, f"Missing field: {field}"
        assert msg["chat_id"] == "5511@c.us"
        assert msg["ack"] == 2
        assert msg["acked_at"] == "2026-06-22T10:00:05.000Z"

    def test_only_own_connection_messages_visible(self, chat_client):
        """Messages tagged with a different connection_id are NOT returned."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id_a = created["id"]
        conn_id_b = str(uuid4())
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id_a, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "on A",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id_b, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "on B",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id_a}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()["items"]
        assert len(msgs) == 1
        assert msgs[0]["body"] == "on A"

    def test_null_chat_id_rows_never_surface(self, chat_client):
        """Pre-migration-040 rows (chat_id IS NULL, not backfilled) must not
        appear on the new indexed thread query — see migration 040's header
        note (the intentional non-backfill decision)."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": None, "raw_sender": "5511@c.us", "direction": "inbound", "body": "pre-040",
             "created_at": "2026-06-01T00:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []


# ── POST /chats/{chat_id}/read (Slice 5, new) ─────────────────────────────────

class TestChatRead:
    def test_marks_read_zeroes_unread_and_publishes(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z",
             "last_message_preview": "hi", "unread_count": 3},
        ])
        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/read", json={}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["chat_id"] == "5511@c.us"
        assert body["unread_count"] == 0
        assert body["last_read_at"] is not None

        # Persisted: a subsequent GET /chats reflects unread_count == 0.
        listed = c.get(f"/api/whatsapp/connections/{conn_id}/chats").json()
        assert listed["items"][0]["unread_count"] == 0

    def test_does_not_await_send_seen(self, chat_client):
        """send_seen fires in the background — the response returns even
        when the FakeWahaClient's send_seen would raise."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z",
             "last_message_preview": "hi"},
        ])

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        class _RaisingFake(FakeWahaClient):
            async def send_seen(self, chat_id, message_id=None, participant=None):
                raise RuntimeError("WAHA unreachable")

        def _raising_factory(*, base_url=None, api_key=None, session="default"):
            return _RaisingFake(session=session)

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _raising_factory
        try:
            resp = c.post(
                f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/read", json={}
            )
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        # The background send_seen failure must NEVER surface as a 5xx here.
        assert resp.status_code == 200, resp.text
        assert resp.json()["unread_count"] == 0

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.post(
            f"/api/whatsapp/connections/{uuid4()}/chats/5511@c.us/read", json={}
        )
        assert resp.status_code == 401, resp.text

    def test_404_other_user_connection(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="OtherRead", base_url="https://waha.example.com", api_key="kr",
        )
        resp = c.post(
            f"/api/whatsapp/connections/{other_conn.id}/chats/5511@c.us/read", json={}
        )
        assert resp.status_code == 404, resp.text

    def test_404_unknown_chat(self, chat_client):
        """A chat_id with no whatsapp_chats row yet is a 404, not a 500."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/never-seen@c.us/read", json={}
        )
        assert resp.status_code == 404, resp.text


# ── No-WAHA-on-read-path assertion (Slice 5 deletion pin) ────────────────────

class TestNoWahaOnReadPath:
    """Pins the deletion: GET /chats and GET /chats/{id}/messages must never
    touch the WAHA client. Uses a FakeWahaClient subclass that raises on
    every method — if either read endpoint still called WAHA, this fails."""

    def test_list_chats_and_list_messages_never_call_waha(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        _seed_chats(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "last_message_at": "2026-06-22T09:00:00.000Z",
             "last_message_preview": "hi"},
        ])
        _seed_messages(db_path, org_id=_TEST_ORG_ID, connection_id=conn_id, rows=[
            {"chat_id": "5511@c.us", "raw_sender": "5511@c.us", "direction": "inbound", "body": "hi",
             "created_at": "2026-06-22T09:00:00.000Z"},
        ])

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        class _ExplodingFake:
            def __getattr__(self, name):
                raise AssertionError(
                    f"WAHA method {name!r} was called — the read path must "
                    "be pure Postgres (Slice 5)."
                )

        def _exploding_factory(*, base_url=None, api_key=None, session="default"):
            return _ExplodingFake()

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _exploding_factory
        try:
            chats_resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
            messages_resp = c.get(
                f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
            )
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        assert chats_resp.status_code == 200, chats_resp.text
        assert messages_resp.status_code == 200, messages_resp.text


# ── POST /chats/{chat_id}/send ────────────────────────────────────────────────

class TestSendMessage:
    def test_send_returns_201_and_message_out(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
            json={"text": "hello world"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["body"] == "hello world"
        assert body["direction"] == "outbound"
        assert body["chat_id"] == "5511@c.us"
        assert "id" in body
        assert "created_at" in body

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.post(
            f"/api/whatsapp/connections/{uuid4()}/chats/5511@c.us/send",
            json={"text": "x"},
        )
        assert resp.status_code == 401, resp.text

    def test_422_empty_text(self, chat_client):
        """Empty string is rejected by Pydantic min_length=1 before WAHA is called."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
            json={"text": ""},
        )
        assert resp.status_code == 422, resp.text

    def test_404_other_user_connection(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="Other3", base_url="https://waha.example.com", api_key="k3",
        )
        resp = c.post(
            f"/api/whatsapp/connections/{other_conn.id}/chats/5511@c.us/send",
            json={"text": "hi"},
        )
        assert resp.status_code == 404, resp.text

    def test_send_persists_outbound_with_connection_id(self, chat_client):
        """The stored message must have connection_id tagged (not null)."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
            json={"text": "tagged msg"},
        )
        assert resp.status_code == 201, resp.text

        # Verify directly in SQLite that connection_id was tagged.
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT connection_id, direction, body FROM conversation_messages WHERE body = ?",
                ("tagged msg",),
            ).fetchone()
        assert row is not None, "Message was not persisted"
        assert row[0] == conn_id, f"connection_id mismatch: {row[0]!r} != {conn_id!r}"
        assert row[1] == "outbound"

    def test_502_on_waha_failure(self, chat_client):
        """FakeWahaClient raises when send_text is given a special trigger."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        from noctusai_lib.integrations.whatsapp import FakeWahaClient as _Fake  # noqa: PLC0415

        class _ErrorFake(_Fake):
            async def send_text(self, chat_id, text):
                raise RuntimeError("WAHA unavailable")

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        def _error_factory(*, base_url=None, api_key=None, session="default"):
            return _ErrorFake(session=session)

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _error_factory
        try:
            resp = c.post(
                f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
                json={"text": "this will fail"},
            )
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        assert resp.status_code == 502, resp.text
        body = resp.json()
        assert body["error"]["code"] == "waha_send_failed", f"unexpected body: {body}"

    def test_send_creates_its_own_chat_row_and_is_visible_immediately(self, chat_client):
        """🔴 REGRESSION PIN. A send must be visible in BOTH reads immediately.

        This test previously asserted the opposite — that the inbox
        "legitimately stays empty until ingest catches up" via WAHA's
        `message.any` echo. That assumption is provably false: the echo carries
        the SAME `provider_message_id`, so `UNIQUE(provider_message_id)` drops
        it as a duplicate and it can never write the row or backfill `chat_id`.
        The message would have been invisible in its own thread permanently,
        not merely until the echo arrived.

        Found on the merged tip of slices 4+5 — each branch was green alone;
        the defect lived only in the seam between them.
        """
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
            json={"text": "hello inbox"},
        )
        assert resp.status_code == 201, resp.text

        # 1. the conversation row exists, with the preview and direction set
        chats_resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert chats_resp.status_code == 200, chats_resp.text
        items = chats_resp.json()["items"]
        assert [i["chat_id"] for i in items] == ["5511@c.us"], chats_resp.text
        assert items[0]["last_message_preview"] == "hello inbox"
        assert items[0]["last_direction"] == "outbound"
        # our own send must never make our own inbox look unread
        assert items[0]["unread_count"] == 0

        # 2. and the message is in its own thread — i.e. chat_id was stamped
        msgs_resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511%40c.us/messages"
        )
        assert msgs_resp.status_code == 200, msgs_resp.text
        bodies = [m["body"] for m in msgs_resp.json()["items"]]
        assert "hello inbox" in bodies, msgs_resp.text


# ── POST /recover (Slice 5, new) ──────────────────────────────────────────────

class TestRecoverConnection:
    def test_recover_returns_ladder_result(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        resp = c.post(f"/api/whatsapp/connections/{conn_id}/recover")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == conn_id
        assert body["stage"]
        assert "status" in body
        assert "paired" in body

    def test_recover_converges_a_stuck_session(self, chat_client):
        """A session whose FakeWahaClient starts stuck (simulating dead
        stored credentials) converges via the ladder, mirroring the live
        fleet incident this endpoint exists to fix."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        fake: FakeWahaClient = fakes["default"]
        fake.simulate_stuck_session()

        resp = c.post(f"/api/whatsapp/connections/{conn_id}/recover")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["stage"] in {"start", "restart", "logout_start", "already_working"}

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.post(f"/api/whatsapp/connections/{uuid4()}/recover")
        assert resp.status_code == 401, resp.text

    def test_404_other_user_connection(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="OtherRecover", base_url="https://waha.example.com", api_key="krec",
        )
        resp = c.post(f"/api/whatsapp/connections/{other_conn.id}/recover")
        assert resp.status_code == 404, resp.text

    def test_502_on_waha_failure(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        class _ErrorFake(FakeWahaClient):
            async def recover_session(self, *, settle_seconds: float = 8.0):
                raise RuntimeError("WAHA unavailable")

        def _error_factory(*, base_url=None, api_key=None, session="default"):
            return _ErrorFake(session=session)

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _error_factory
        try:
            resp = c.post(f"/api/whatsapp/connections/{conn_id}/recover")
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        assert resp.status_code == 502, resp.text


# ── GET /stream (Slice 5, new — SSE) ──────────────────────────────────────────

class _FiniteBus:
    """``RealtimeBus`` double whose ``subscribe()`` yields nothing then
    RETURNS — lets a router-level ``TestClient`` request terminate
    naturally instead of hanging. Mirrors ``noctusai_lib.realtime``'s own
    test suite's ``_FiniteBus``: per that module's docstring, ``TestClient``
    fully drives the ASGI response to completion before returning anything
    at all, so a genuinely-live (never-terminating) bus subscription would
    hang the whole test, not just a partial read."""

    async def publish(self, scope, event, payload):
        raise NotImplementedError("not used by these tests")

    async def subscribe(self, scope, *, last_event_id=None):
        return
        yield  # pragma: no cover — makes this an async generator


class TestStream:
    def test_headers_are_sse_and_no_buffering(self, chat_client, monkeypatch):
        """Swap the module-level ``_whatsapp_bus`` (the seam
        ``whatsapp_connections_router`` ships specifically for this — see
        its "Realtime stream (SSE)" section) for a ``_FiniteBus`` so the
        request completes; asserts the headers `create_sse_router` sets."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        import app.routers.whatsapp_connections_router as wcr  # noqa: PLC0415
        monkeypatch.setattr(wcr, "_whatsapp_bus", _FiniteBus())

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/stream")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["x-accel-buffering"] == "no"
        assert resp.headers["cache-control"] == "no-cache"

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.get(f"/api/whatsapp/connections/{uuid4()}/stream")
        assert resp.status_code == 401, resp.text

    def test_404_rejects_a_caller_who_does_not_own_the_connection(self, chat_client):
        """A subscriber must never be able to attach to a scope they cannot
        read — the auth_dependency runs `_require_record` BEFORE the SSE
        response (or its stream) is ever constructed."""
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="OtherStream", base_url="https://waha.example.com", api_key="kstream",
        )
        resp = c.get(f"/api/whatsapp/connections/{other_conn.id}/stream")
        assert resp.status_code == 404, resp.text


# ── PUT /auto-reply ───────────────────────────────────────────────────────────

class TestAutoReply:
    def test_auto_reply_default_false_in_connection_response(self, chat_client):
        """Newly created connection carries auto_reply_enabled=false."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        assert created["auto_reply_enabled"] is False

    def test_put_auto_reply_enables_toggle(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        resp = c.put(
            f"/api/whatsapp/connections/{conn_id}/auto-reply",
            json={"enabled": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == conn_id
        assert body["auto_reply_enabled"] is True

    def test_put_auto_reply_disables_toggle(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        c.put(f"/api/whatsapp/connections/{conn_id}/auto-reply", json={"enabled": True})
        resp = c.put(f"/api/whatsapp/connections/{conn_id}/auto-reply", json={"enabled": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()["auto_reply_enabled"] is False

    def test_put_auto_reply_404_other_user(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        other_org = UUID("00000000-0000-4000-8000-000000000001")
        other_user = UUID("00000000-0000-4000-8000-0000000000bb")
        other_conn = conn_store.create_connection(
            org_id=other_org, user_id=other_user,
            label="Other4", base_url="https://waha.example.com", api_key="k4",
        )
        resp = c.put(
            f"/api/whatsapp/connections/{other_conn.id}/auto-reply",
            json={"enabled": True},
        )
        assert resp.status_code == 404, resp.text

    def test_401_unauthenticated(self, chat_client):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
        tc = TestClient(app, raise_server_exceptions=False)
        resp = tc.put(
            f"/api/whatsapp/connections/{uuid4()}/auto-reply",
            json={"enabled": True},
        )
        assert resp.status_code == 401, resp.text

    def test_put_auto_reply_reflects_in_get_connection(self, chat_client):
        """GET /connections/{id} shows the updated auto_reply_enabled value."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        c.put(f"/api/whatsapp/connections/{conn_id}/auto-reply", json={"enabled": True})

        # GET /connections lists the connection; check auto_reply_enabled flipped.
        listed = c.get("/api/whatsapp/connections")
        assert listed.status_code == 200, listed.text
        conn_row = next((r for r in listed.json() if r["id"] == conn_id), None)
        assert conn_row is not None
        assert conn_row["auto_reply_enabled"] is True


# ── start_session NOWEB payload ───────────────────────────────────────────────
# Unaffected by Slice 5 — session admin, not the chat-inbox read path.

class TestStartSessionNoweb:
    """start_session payload includes NOWEB store config."""

    def test_create_connection_includes_noweb_config_in_start_payload(
        self, chat_client, monkeypatch
    ):
        """After connection create, the FakeWahaClient captured a start_session call.

        We verify the REAL WahaClient sends the config by inspecting what
        httpx.AsyncClient.post receives (monkeypatched at the httpx level).
        For the Fake path (used in fixtures) the test verifies the session was
        started (start_count > 0) — the Fake doesn't accept payload kwargs but
        the Real builds it internally.
        """
        c, conn_store, fakes, db_path = chat_client
        # _create_connection triggers create_connection which calls start_session.
        _create_connection(c)
        fake: FakeWahaClient = fakes["default"]
        assert fake.start_count >= 1, "start_session was never called"

    def test_real_client_start_session_sends_noweb_payload(self, monkeypatch):
        """WahaClient.start_session POSTs the noweb store config in the JSON body."""
        import asyncio  # noqa: PLC0415
        import httpx  # noqa: PLC0415
        from unittest.mock import AsyncMock, MagicMock  # noqa: PLC0415
        from noctusai_lib.integrations.whatsapp.client import WahaClient  # noqa: PLC0415

        posted_bodies: list[dict] = []

        class _FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def post(self, url, *, json=None, headers=None):
                posted_bodies.append(json or {})
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.content = b'{"name":"default","status":"SCAN_QR_CODE"}'
                mock_resp.raise_for_status = MagicMock()

                def _json():
                    import json as _json_mod  # noqa: PLC0415
                    return _json_mod.loads(mock_resp.content)

                mock_resp.json = _json
                return mock_resp

        monkeypatch.setattr(httpx, "AsyncClient", lambda **_: _FakeAsyncClient())

        client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
        asyncio.run(client.start_session())

        assert len(posted_bodies) == 1
        body = posted_bodies[0]
        noweb = body.get("config", {}).get("noweb", {}).get("store", {})
        assert noweb.get("enabled") is True, f"noweb.store.enabled missing in: {body}"
        assert noweb.get("fullSync") is True, f"noweb.store.fullSync missing in: {body}"
        # 🔴 Regression pin. WAHA's key is camelCase `fullSync`. This assertion
        # previously named the snake_case spelling, so it passed against a payload
        # WAHA silently DROPPED — the live session reported `fullSync: false` for
        # weeks while this test stayed green. Asserting the absence of the wrong
        # key is what makes the false-green unrepeatable.
        assert "full_sync" not in noweb, f"snake_case full_sync must never be sent: {body}"

    def test_real_client_restart_session_sends_noweb_payload(self, monkeypatch):
        """WahaClient.restart_session POSTs the noweb store config in the JSON body."""
        import asyncio  # noqa: PLC0415
        import httpx  # noqa: PLC0415
        from unittest.mock import MagicMock  # noqa: PLC0415
        from noctusai_lib.integrations.whatsapp.client import WahaClient  # noqa: PLC0415

        posted_bodies: list[dict] = []

        class _FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def post(self, url, *, json=None, headers=None):
                posted_bodies.append(json or {})
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.content = b'{"name":"default","status":"WORKING"}'
                mock_resp.raise_for_status = MagicMock()

                def _json():
                    import json as _json_mod  # noqa: PLC0415
                    return _json_mod.loads(mock_resp.content)

                mock_resp.json = _json
                return mock_resp

        monkeypatch.setattr(httpx, "AsyncClient", lambda **_: _FakeAsyncClient())

        client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
        asyncio.run(client.restart_session())

        assert len(posted_bodies) == 1
        body = posted_bodies[0]
        noweb = body.get("config", {}).get("noweb", {}).get("store", {})
        assert noweb.get("enabled") is True, f"noweb.store.enabled missing in: {body}"
        assert noweb.get("fullSync") is True, f"noweb.store.fullSync missing in: {body}"
        # 🔴 Regression pin. WAHA's key is camelCase `fullSync`. This assertion
        # previously named the snake_case spelling, so it passed against a payload
        # WAHA silently DROPPED — the live session reported `fullSync: false` for
        # weeks while this test stayed green. Asserting the absence of the wrong
        # key is what makes the false-green unrepeatable.
        assert "full_sync" not in noweb, f"snake_case full_sync must never be sent: {body}"
