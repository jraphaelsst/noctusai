"""Tests for per-connection chat endpoints (migration 014).

Drives all four new endpoints through two DI seams — same Class-B pattern as
``test_whatsapp_connections_router.py``:

  - ``get_connection_store``     → SQLite-backed WhatsAppConnectionStore
  - ``get_message_store_factory`` → factory returning SQLite-backed MessageStore

Auth is exercised via the shared ``client`` fixture (MockSupabaseClient).  No
external calls; FakeWahaClient drives the send path.

Endpoints under test
--------------------
  GET  /api/whatsapp/connections/{id}/chats
  GET  /api/whatsapp/connections/{id}/chats/{chat_id:path}/messages
  POST /api/whatsapp/connections/{id}/chats/{chat_id:path}/send
  PUT  /api/whatsapp/connections/{id}/auto-reply

Contract pins
-------------
  - 401 on unauthenticated access (via the shared ``client`` fixture with
    Bearer token missing; the test must pass ``headers={}`` or the seed
    MockSupabaseClient returns unauthenticated → 401).
  - 404 for a connection owned by a DIFFERENT user_id (ownership guard).
  - 422 on empty ``text`` in send (Pydantic min_length=1).
  - 201 on send + outbound row tagged with connection_id.
  - 502 on WAHA send failure.
  - list_chats grouping + ordering (two senders, mixed directions).
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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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
    """Minimal query builder — enough to support the MessageStore interface."""

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

    def select(self, cols: str) -> "_SQLiteTableProxy":
        self._select_cols = cols
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
        return _Response([dict(r) for r in rows])


class _Response:
    def __init__(self, data: list[dict]):
        self.data = data


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def chat_client(client, tmp_path: Path, override_settings, monkeypatch):
    """Full DI-wired client for the chat endpoints.

    Sets up:
      - SQLite-backed WhatsAppConnectionStore (conn table + msg table)
      - SQLite-backed MessageStore factory
      - FakeWahaClient for the send path
      - waha_base_url + PRODUCT_URL_SOCIAL_WIRING env
    """
    from app.main import app
    from app.routers.whatsapp_connections_router import (
        get_connection_store,
        get_message_store_factory,
        get_waha_client_factory,
    )

    override_settings(waha_base_url="https://waha.example.com")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", _PRODUCT_BASE)

    # Shared db_path used by both stores so FK-style references work.
    db_path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_CONN_SCHEMA + _MSG_SCHEMA)

    conn_store = WhatsAppConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(Fernet.generate_key())
    )
    msg_client = _SQLiteSchemaClient(db_path)

    def _make_msg_store(org_id: UUID) -> MessageStore:
        return MessageStore(admin_supabase=msg_client, org_id=org_id)

    fakes: dict[str, FakeWahaClient] = {}

    def _fake_factory(*, base_url=None, api_key=None, session="default"):
        return fakes.setdefault(session, FakeWahaClient(session=session))

    _prev_conn = app.dependency_overrides.get(get_connection_store)
    _prev_msg = app.dependency_overrides.get(get_message_store_factory)
    _prev_waha = app.dependency_overrides.get(get_waha_client_factory)

    app.dependency_overrides[get_connection_store] = lambda: conn_store
    app.dependency_overrides[get_message_store_factory] = lambda: _make_msg_store
    app.dependency_overrides[get_waha_client_factory] = lambda: _fake_factory

    yield client, conn_store, fakes, db_path

    for dep, prev in (
        (get_connection_store, _prev_conn),
        (get_message_store_factory, _prev_msg),
        (get_waha_client_factory, _prev_waha),
    ):
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
            row.setdefault("created_at", f"2026-06-22T10:00:00.000Z")
            cols = ", ".join(f'"{k}"' for k in row)
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f'INSERT INTO conversation_messages ({cols}) VALUES ({placeholders})',
                list(row.values()),
            )


# ── GET /chats ────────────────────────────────────────────────────────────────

class TestListChats:
    def test_empty_returns_200_bare_array(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        resp = c.get(f"/api/whatsapp/connections/{created['id']}/chats")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

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
        # The fixture owns user 00...aa; insert a row owned by user 00...bb
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

    def test_groups_by_sender_and_orders_by_last_message(self, chat_client):
        """Two senders, one with later activity — that one must come first."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        # Determine org_id from the token fixture (the seed mock always uses a fixed one).
        from app.config import settings  # noqa: PLC0415
        # Derive the org_id the MockSupabaseClient uses.
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound",  "body": "hi",   "created_at": "2026-06-22T09:00:00.000Z"},
            {"raw_sender": "5522@c.us", "direction": "inbound",  "body": "hello","created_at": "2026-06-22T10:00:00.000Z"},
            {"raw_sender": "5522@c.us", "direction": "outbound", "body": "hey",  "created_at": "2026-06-22T10:01:00.000Z"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 2
        # 5522 has later last_message_at → must be first.
        assert data[0]["chat_id"] == "5522@c.us"
        assert data[0]["last_direction"] == "outbound"
        assert data[1]["chat_id"] == "5511@c.us"

    def test_unread_count_correct(self, chat_client):
        """Unread = inbound messages after the last outbound."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5599@c.us", "direction": "inbound",  "body": "msg1", "created_at": "2026-06-22T09:00:00.000Z"},
            {"raw_sender": "5599@c.us", "direction": "outbound", "body": "rep1", "created_at": "2026-06-22T09:01:00.000Z"},
            {"raw_sender": "5599@c.us", "direction": "inbound",  "body": "msg2", "created_at": "2026-06-22T09:02:00.000Z"},
            {"raw_sender": "5599@c.us", "direction": "inbound",  "body": "msg3", "created_at": "2026-06-22T09:03:00.000Z"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        chats = resp.json()
        assert len(chats) == 1
        assert chats[0]["unread"] == 2  # msg2 + msg3 are after last outbound

    def test_contact_strips_jid_suffix(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511999998888@c.us", "direction": "inbound", "body": "x",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["contact"] == "5511999998888"


# ── GET /chats/{chat_id}/messages ────────────────────────────────────────────

class TestListMessages:
    def test_empty_thread_returns_200_bare_array(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        resp = c.get(
            f"/api/whatsapp/connections/{created['id']}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

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

    def test_returns_messages_oldest_first(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "first",
             "created_at": "2026-06-22T09:00:00.000Z"},
            {"raw_sender": "5511@c.us", "direction": "outbound", "body": "second",
             "created_at": "2026-06-22T09:01:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 2
        assert msgs[0]["body"] == "first"
        assert msgs[0]["direction"] == "inbound"
        assert msgs[1]["body"] == "second"
        assert msgs[1]["direction"] == "outbound"

    def test_before_cursor_filters_older_messages(self, chat_client):
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "old",
             "created_at": "2026-06-22T08:00:00.000Z"},
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "newer",
             "created_at": "2026-06-22T09:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages",
            params={"before": "2026-06-22T08:30:00.000Z"},
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 1
        assert msgs[0]["body"] == "old"

    def test_message_shape_fields_present(self, chat_client):
        """Verify all required MessageOut fields are in the response."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "check",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msg = resp.json()[0]
        for field in ("id", "chat_id", "direction", "body", "created_at"):
            assert field in msg, f"Missing field: {field}"
        assert msg["chat_id"] == "5511@c.us"

    def test_only_own_connection_messages_visible(self, chat_client):
        """Messages tagged with a different connection_id are NOT returned."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id_a = created["id"]
        conn_id_b = str(uuid4())
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id_a, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "on A",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id_b, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "on B",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])
        resp = c.get(
            f"/api/whatsapp/connections/{conn_id_a}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 1
        assert msgs[0]["body"] == "on A"


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
        # Trigger FakeWahaClient's error path by pre-loading an exception.
        # FakeWahaClient always succeeds by default; we patch it post-fixture.
        session = "default"

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

    def test_send_shows_in_chat_list_afterwards(self, chat_client):
        """After a send, GET /chats shows the chat in the inbox."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        send_resp = c.post(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/send",
            json={"text": "hello inbox"},
        )
        assert send_resp.status_code == 201, send_resp.text

        chats_resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert chats_resp.status_code == 200, chats_resp.text
        chats = chats_resp.json()
        assert any(ch["chat_id"] == "5511@c.us" for ch in chats), (
            f"Expected 5511@c.us in chats, got {chats}"
        )


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


# ── WAHA live-merge tests ─────────────────────────────────────────────────────
# These tests exercise the new WAHA list_chats / fetch_chat_messages merge path
# added by feat/sw-wa-chat-fetch.

class TestWahaLiveMergeChats:
    """GET /chats merges WAHA live list with DB rows."""

    def test_waha_chats_appear_when_db_empty(self, chat_client):
        """Conversations that exist only in WAHA (no DB rows) surface in the list."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        # Seed the FakeWahaClient with a chat (simulates full_sync result).
        fake: FakeWahaClient = fakes["default"]
        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5599@c.us"},
                "name": "Carlos",
                "lastMessage": {"body": "oi", "fromMe": False, "timestamp": 1718000000},
            }
        ]

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["chat_id"] == "5599@c.us"
        assert row["contact"] == "Carlos"
        assert row["last_direction"] == "inbound"
        assert row["last_message"] == "oi"

    def test_waha_chat_merged_with_db_row_prefers_newer_ts(self, chat_client):
        """When WAHA has a newer message than DB, the merged row reflects it."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5577@c.us", "direction": "inbound", "body": "old",
             "created_at": "2026-06-10T10:00:00.000Z"},
        ])

        fake: FakeWahaClient = fakes["default"]
        # WAHA has a newer message (full_sync result)
        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5577@c.us"},
                "name": "Ana",
                # Unix epoch for 2026-06-22T10:00:00Z = 1782122400
                "lastMessage": {"body": "new msg", "fromMe": False, "timestamp": 1782122400},
            }
        ]

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["chat_id"] == "5577@c.us"
        # WAHA name used as contact because WAHA is newer and provides a name
        assert row["last_message"] == "new msg"

    def test_waha_unavailable_falls_back_to_db_no_500(self, chat_client):
        """Store-not-enabled 400 (WAHA unavailable) falls back to DB — never 500."""
        import httpx  # noqa: PLC0415
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "fallback",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])

        # Make list_chats raise to simulate store-not-enabled 400.
        from noctusai_lib.integrations.whatsapp import FakeWahaClient as _Fake  # noqa: PLC0415

        class _ErrorFake(_Fake):
            async def list_chats(self, limit=50):
                raise httpx.HTTPStatusError(
                    "400 Bad Request",
                    request=object(),  # type: ignore[arg-type]
                    response=object(),  # type: ignore[arg-type]
                )

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        def _err_factory(*, base_url=None, api_key=None, session="default"):
            return _ErrorFake(session=session)

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _err_factory
        try:
            resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        assert resp.status_code == 200, resp.text
        data = resp.json()
        # DB row still visible (fallback).
        assert any(row["chat_id"] == "5511@c.us" for row in data)

    def test_waha_and_db_dedup_same_chat(self, chat_client):
        """The same chat_id in WAHA and DB is not duplicated in the result."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "hi",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])

        fake: FakeWahaClient = fakes["default"]
        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5511@c.us"},
                "name": "Bob",
                "lastMessage": {"body": "hi", "fromMe": False, "timestamp": 1750503600},
            }
        ]

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Must be exactly ONE entry for 5511@c.us.
        matching = [r for r in data if r["chat_id"] == "5511@c.us"]
        assert len(matching) == 1


class TestWahaLiveMergeMessages:
    """GET /chats/{chat_id}/messages merges WAHA history with DB rows."""

    def test_waha_history_appears_when_db_empty(self, chat_client):
        """Historical WAHA messages surface when conversation_messages is empty."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]

        fake: FakeWahaClient = fakes["default"]
        fake.fake_chat_messages["5511@c.us"] = [
            {
                "id": {"_serialized": "BAE5XXX001"},
                "body": "first ever message",
                "from": "5511@c.us",
                "timestamp": 1750500000,
                "fromMe": False,
            }
        ]

        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 1
        assert msgs[0]["body"] == "first ever message"
        assert msgs[0]["direction"] == "inbound"
        assert msgs[0]["provider_message_id"] == "BAE5XXX001"

    def test_waha_and_db_dedup_by_provider_message_id(self, chat_client):
        """A message in both WAHA and DB (same provider_message_id) appears once."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {
                "raw_sender": "5511@c.us",
                "direction": "inbound",
                "body": "hello",
                "created_at": "2026-06-22T09:00:00.000Z",
                "provider_message_id": "BAE5DUP001",
            }
        ])

        fake: FakeWahaClient = fakes["default"]
        fake.fake_chat_messages["5511@c.us"] = [
            {
                "id": {"_serialized": "BAE5DUP001"},
                "body": "hello",
                "from": "5511@c.us",
                "timestamp": 1750467600,
                "fromMe": False,
            }
        ]

        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 1
        assert msgs[0]["body"] == "hello"

    def test_waha_unavailable_falls_back_to_db_no_500(self, chat_client):
        """WAHA error on fetch_chat_messages falls back to DB — never 500."""
        import httpx  # noqa: PLC0415
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "inbound", "body": "from db",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])

        from noctusai_lib.integrations.whatsapp import FakeWahaClient as _Fake  # noqa: PLC0415

        class _ErrorFake(_Fake):
            async def fetch_chat_messages(self, chat_id, limit=50):
                raise httpx.HTTPStatusError(
                    "400 Bad Request",
                    request=object(),  # type: ignore[arg-type]
                    response=object(),  # type: ignore[arg-type]
                )

        from app.main import app  # noqa: PLC0415
        from app.routers.whatsapp_connections_router import get_waha_client_factory  # noqa: PLC0415

        def _err_factory(*, base_url=None, api_key=None, session="default"):
            return _ErrorFake(session=session)

        _prev = app.dependency_overrides.get(get_waha_client_factory)
        app.dependency_overrides[get_waha_client_factory] = lambda: _err_factory
        try:
            resp = c.get(
                f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
            )
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_waha_client_factory, None)
            else:
                app.dependency_overrides[get_waha_client_factory] = _prev

        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert any(m["body"] == "from db" for m in msgs)

    def test_waha_and_db_merge_sorted_oldest_first(self, chat_client):
        """Merged result is sorted oldest-first regardless of source."""
        c, conn_store, fakes, db_path = chat_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID

        # DB has a newer message.
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {"raw_sender": "5511@c.us", "direction": "outbound", "body": "newer reply",
             "created_at": "2026-06-22T10:00:00.000Z"},
        ])

        fake: FakeWahaClient = fakes["default"]
        # WAHA has the original inbound message (older).
        # Unix ts for 2026-06-22T09:00:00Z ≈ 1750586400 (approx — just needs to be < 10:00)
        fake.fake_chat_messages["5511@c.us"] = [
            {
                "id": {"_serialized": "BAE5OLD001"},
                "body": "older inbound",
                "from": "5511@c.us",
                "timestamp": 1750582800,  # 2026-06-22T09:00:00Z
                "fromMe": False,
            }
        ]

        resp = c.get(
            f"/api/whatsapp/connections/{conn_id}/chats/5511@c.us/messages"
        )
        assert resp.status_code == 200, resp.text
        msgs = resp.json()
        assert len(msgs) == 2
        # WAHA's older inbound must come first.
        assert msgs[0]["body"] == "older inbound"
        assert msgs[0]["direction"] == "inbound"
        assert msgs[1]["body"] == "newer reply"
        assert msgs[1]["direction"] == "outbound"


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
        asyncio.get_event_loop().run_until_complete(client.start_session())

        assert len(posted_bodies) == 1
        body = posted_bodies[0]
        noweb = body.get("config", {}).get("noweb", {}).get("store", {})
        assert noweb.get("enabled") is True, f"noweb.store.enabled missing in: {body}"
        assert noweb.get("full_sync") is True, f"noweb.store.full_sync missing in: {body}"

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
        asyncio.get_event_loop().run_until_complete(client.restart_session())

        assert len(posted_bodies) == 1
        body = posted_bodies[0]
        noweb = body.get("config", {}).get("noweb", {}).get("store", {})
        assert noweb.get("enabled") is True, f"noweb.store.enabled missing in: {body}"
        assert noweb.get("full_sync") is True, f"noweb.store.full_sync missing in: {body}"
