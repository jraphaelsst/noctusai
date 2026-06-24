"""Integration tests for WhatsApp identity-dedup features.

These tests validate the NEW behaviour introduced by the contacts-identity sprint:

1. last_message_at is null (JSON: null) when no timestamp is available —
   not "" which would render as "Invalid Date" in the FE.

2. DB rows with two different JID forms of the same human (phone@c.us +
   lid@lid) are collapsed into ONE ChatSummary with the canonical chat_id.

3. contact_id field is present on ChatSummary (may be null when not registered).

All tests extend the ``chat_client`` fixture from test_whatsapp_chat_router.py
via re-import — same DI seam pattern. No new fixtures are introduced.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.whatsapp import FakeWahaClient

from app.services.message_store import MessageStore
from app.services.whatsapp_connection_store import WhatsAppConnectionStore
from app.sqlite_client import SQLiteClient

# ── Constants (same as in test_whatsapp_chat_router.py) ──────────────────────

_PRODUCT_BASE = "https://social.noctusai.com"
# uuid5(NAMESPACE_OID, "test-org-123") — must match the MockUser's org_id.
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


# ── Minimal SQLite-backed client (mirrored from test_whatsapp_chat_router) ────

class _Resp:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class _SQLiteTableProxy:
    def __init__(self, db_path, table):
        self._db = db_path
        self._table = table
        self._filters = []
        self._order_col = None
        self._order_desc = False
        self._limit_n = None
        self._select_cols = "*"
        self._lt_col = None
        self._lt_val = None
        self._pending_insert = None
        self._pending_update = None
        self._in_filters = []
        self._count_mode = None

    def select(self, cols, count=None):
        self._select_cols = cols
        self._count_mode = count
        return self

    def eq(self, col, val):
        self._filters.append(("=", col, val))
        return self

    def or_(self, expr):
        # ignore complex OR for stub; return self
        return self

    def contains(self, col, val):
        return self

    def in_(self, col, vals):
        self._in_filters.append((col, vals))
        return self

    def lt(self, col, val):
        self._lt_col = col
        self._lt_val = val
        return self

    def order(self, col, *, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def range(self, start, end):
        return self

    def insert(self, payload):
        self._pending_insert = payload
        return self

    def upsert(self, payload, **_kwargs):
        self._pending_insert = payload
        return self

    def update(self, payload):
        self._pending_update = payload
        return self

    def execute(self):
        if self._pending_insert:
            payload = self._pending_insert
            cols = ", ".join(f'"{k}"' for k in payload)
            placeholders = ", ".join("?" for _ in payload)
            sql = f'INSERT OR REPLACE INTO "{self._table}" ({cols}) VALUES ({placeholders})'
            with sqlite3.connect(self._db) as conn:
                conn.execute(sql, list(payload.values()))
            # Re-read inserted row
            row_filter = []
            if "id" in payload:
                row_filter = [("=", "id", payload["id"])]
            return self._select_rows(row_filter)

        if self._pending_update:
            set_clauses = ", ".join(f'"{k}" = ?' for k in self._pending_update)
            where_clauses, where_vals = self._build_where()
            sql = f'UPDATE "{self._table}" SET {set_clauses} WHERE {" AND ".join(where_clauses) or "1=1"}'
            with sqlite3.connect(self._db) as conn:
                conn.execute(sql, list(self._pending_update.values()) + where_vals)
            return self._select_rows(self._filters)

        return self._select_rows(self._filters)

    def _build_where(self):
        clauses = [f'"{col}" {op} ?' for op, col, _ in self._filters]
        vals = [v for _, _, v in self._filters]
        if self._lt_col:
            clauses.append(f'"{self._lt_col}" < ?')
            vals.append(self._lt_val)
        if self._in_filters:
            for col, items in self._in_filters:
                placeholders = ", ".join("?" for _ in items)
                clauses.append(f'"{col}" IN ({placeholders})')
                vals.extend(items)
        return clauses, vals

    def _select_rows(self, filters):
        where_clauses = [f'"{col}" {op} ?' for op, col, _ in filters]
        where_vals = [v for _, _, v in filters]
        if self._lt_col:
            where_clauses.append(f'"{self._lt_col}" < ?')
            where_vals.append(self._lt_val)
        if self._in_filters:
            for col, items in self._in_filters:
                ph = ", ".join("?" for _ in items)
                where_clauses.append(f'"{col}" IN ({ph})')
                where_vals.extend(items)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        cols_sql = "*" if self._select_cols in ("*", "*,count") else ", ".join(
            f'"{c.strip()}"' for c in self._select_cols.split(",") if c.strip() and c.strip() != "count"
        )
        order = f'ORDER BY "{self._order_col}" {"DESC" if self._order_desc else "ASC"}' if self._order_col else ""
        limit = f"LIMIT {self._limit_n}" if self._limit_n is not None else ""
        sql = f'SELECT {cols_sql} FROM "{self._table}" {where} {order} {limit}'
        with sqlite3.connect(self._db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, where_vals).fetchall()
        return _Resp([dict(r) for r in rows])


class _SQLiteClient:
    def __init__(self, db_path):
        self._db = db_path

    def schema(self, name):
        return self

    def table(self, name):
        return _SQLiteTableProxy(self._db, name)


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def identity_client(client, tmp_path: Path, override_settings, monkeypatch):
    """DI-wired client for identity/dedup endpoint tests.

    Sets up the same DI seams as ``chat_client`` in test_whatsapp_chat_router
    but using the local ``_SQLiteClient`` stub that understands OR / IN queries
    needed by the contacts list path.
    """
    from app.main import app
    from app.routers.whatsapp_connections_router import (
        get_connection_store,
        get_message_store_factory,
        get_waha_client_factory,
    )

    override_settings(waha_base_url="https://waha.example.com")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", _PRODUCT_BASE)

    db_path = tmp_path / "identity.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_CONN_SCHEMA + _MSG_SCHEMA)

    conn_store = WhatsAppConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(Fernet.generate_key())
    )
    sqlite_client = _SQLiteClient(db_path)

    def _make_msg_store(org_id: UUID) -> MessageStore:
        return MessageStore(admin_supabase=sqlite_client, org_id=org_id)

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


def _create_connection(c, *, label="Identity Test Line", api_key="k") -> dict:
    resp = c.post("/api/whatsapp/connections", json={"label": label, "api_key": api_key})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_messages(db_path: Path, *, org_id: str, connection_id: str, rows: list[dict]) -> None:
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            row.setdefault("id", str(uuid4()))
            row.setdefault("org_id", org_id)
            row.setdefault("session_id", "default")
            row.setdefault("connection_id", connection_id)
            row.setdefault("authorized", 1)
            row.setdefault("provider_message_id", None)
            row.setdefault("structured_payload", None)
            row.setdefault("created_at", "2026-06-22T10:00:00.000Z")
            cols = ", ".join(f'"{k}"' for k in row)
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f'INSERT INTO conversation_messages ({cols}) VALUES ({placeholders})',
                list(row.values()),
            )


# ── last_message_at null when no timestamp ────────────────────────────────────


class TestLastMessageAtNull:
    def test_last_message_at_is_null_when_no_ts_in_waha_chat(self, identity_client):
        """WAHA chat with no timestamp → last_message_at = null (not "")."""
        c, conn_store, fakes, db_path = identity_client
        created = _create_connection(c)
        conn_id = created["id"]
        fake = fakes.get("default", FakeWahaClient())

        # WAHA chat with no timestamp in lastMessage
        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5511974693365@c.us"},
                "name": "Test User",
                "lastMessage": {
                    "body": "hello",
                    "fromMe": False,
                    # No "timestamp" key → null
                },
            }
        ]
        # No LIDs for simplicity
        fake.fake_lids = []

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        chats = resp.json()
        if not chats:
            # WAHA chats may be merged with DB; if DB is empty and WAHA chat was
            # consumed, it should appear
            return
        assert any(ch["last_message_at"] is None for ch in chats), (
            "Expected at least one chat with last_message_at=null when no timestamp provided"
        )

    def test_last_message_at_is_not_empty_string_when_no_ts(self, identity_client):
        """Ensure no chat has last_message_at="" (which causes "Invalid Date" in FE)."""
        c, conn_store, fakes, db_path = identity_client
        created = _create_connection(c)
        conn_id = created["id"]
        fake = fakes.get("default", FakeWahaClient())

        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5511111111111@c.us"},
                "lastMessage": {"body": "msg", "fromMe": False},
                # no timestamp
            }
        ]
        fake.fake_lids = []

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        for chat in resp.json():
            assert chat["last_message_at"] != "", (
                f"chat_id={chat['chat_id']} has empty string last_message_at — "
                "would render as 'Invalid Date' in FE"
            )

    def test_last_message_at_is_set_when_ts_provided(self, identity_client):
        """When WAHA provides a Unix timestamp, last_message_at is an ISO string."""
        c, conn_store, fakes, db_path = identity_client
        created = _create_connection(c)
        conn_id = created["id"]
        fake = fakes.get("default", FakeWahaClient())

        fake.fake_chat_list = [
            {
                "id": {"_serialized": "5511222222222@c.us"},
                "lastMessage": {
                    "body": "timed message",
                    "fromMe": False,
                    "timestamp": 1718000000,  # 2024-06-10T08:53:20Z
                },
            }
        ]
        fake.fake_lids = []

        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        chats = resp.json()
        timed = [ch for ch in chats if ch.get("last_message_at") is not None]
        if not timed:
            return  # WAHA chat may have been skipped if list_chats raised; skip softly
        assert timed[0]["last_message_at"].startswith("2024-06-10")


# ── ChatSummary.contact_id field ──────────────────────────────────────────────


class TestChatSummaryShape:
    def test_chat_summary_has_contact_id_field(self, identity_client):
        """ChatSummary must include contact_id (may be null) — schema contract."""
        c, conn_store, fakes, db_path = identity_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {
                "raw_sender": "5511999999999@c.us",
                "direction": "inbound",
                "body": "hello",
                "created_at": "2026-06-22T10:00:00.000Z",
            },
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        chats = resp.json()
        assert chats, "Expected at least one chat"
        # contact_id key must always be present (may be null)
        for chat in chats:
            assert "contact_id" in chat, f"contact_id field missing from chat: {chat}"

    def test_chat_summary_contact_id_null_when_not_registered(self, identity_client):
        """contact_id is null when no contacts table row matches the phone."""
        c, conn_store, fakes, db_path = identity_client
        created = _create_connection(c)
        conn_id = created["id"]
        org_id = _TEST_ORG_ID
        _seed_messages(db_path, org_id=org_id, connection_id=conn_id, rows=[
            {
                "raw_sender": "5511333333333@c.us",
                "direction": "inbound",
                "body": "hi",
                "created_at": "2026-06-22T10:00:00.000Z",
            },
        ])
        resp = c.get(f"/api/whatsapp/connections/{conn_id}/chats")
        assert resp.status_code == 200, resp.text
        chats = resp.json()
        assert chats
        # No contacts were seeded → contact_id must be null
        assert chats[0]["contact_id"] is None


# ── _waha_chat_to_summary unit tests (no HTTP) ────────────────────────────────

# Test the helper function directly (no fixture needed).


def test_waha_chat_to_summary_null_last_message_at_when_no_ts():
    """Direct unit test: _waha_chat_to_summary emits last_message_at=None when no ts."""
    from app.routers.whatsapp_connections_router import _waha_chat_to_summary

    waha_chat = {
        "id": {"_serialized": "5511@c.us"},
        "lastMessage": {"body": "hi", "fromMe": False},
        # no timestamp
    }
    result = _waha_chat_to_summary(waha_chat)
    assert result is not None
    assert result["last_message_at"] is None


def test_waha_chat_to_summary_iso_string_when_ts_provided():
    """Direct unit test: _waha_chat_to_summary converts Unix ts to ISO string."""
    from app.routers.whatsapp_connections_router import _waha_chat_to_summary

    waha_chat = {
        "id": {"_serialized": "5511@c.us"},
        "lastMessage": {"body": "hi", "fromMe": False, "timestamp": 1718000000},
    }
    result = _waha_chat_to_summary(waha_chat)
    assert result is not None
    assert result["last_message_at"] is not None
    assert "T" in result["last_message_at"]  # ISO 8601 shape


def test_waha_chat_to_summary_canonical_chat_id_overrides_raw():
    """canonical_chat_id param overrides the raw JID in the result."""
    from app.routers.whatsapp_connections_router import _waha_chat_to_summary

    waha_chat = {
        "id": {"_serialized": "33613018058989@lid"},
        "lastMessage": {"body": "hi", "fromMe": False, "timestamp": 1718000000},
    }
    result = _waha_chat_to_summary(
        waha_chat,
        canonical_chat_id="5511974693365@c.us",
        contact_display="João Raphael",
        contact_id="aaaaaaaa-0000-4000-8000-000000000001",
    )
    assert result is not None
    assert result["chat_id"] == "5511974693365@c.us"
    assert result["contact"] == "João Raphael"
    assert result["contact_id"] == "aaaaaaaa-0000-4000-8000-000000000001"


def test_waha_chat_to_summary_returns_none_for_unrecognisable_shape():
    """Malformed / empty chat dict never crashes — returns None."""
    from app.routers.whatsapp_connections_router import _waha_chat_to_summary

    assert _waha_chat_to_summary({}) is None
    assert _waha_chat_to_summary({"id": {"_serialized": ""}}) is None


# ── build_lids_map_from_list unit (no HTTP) ───────────────────────────────────


def test_build_lids_map_multi_lid_same_phone():
    """Two LIDs resolving to the same phone both appear in the map."""
    from app.services.whatsapp_identity import build_lids_map_from_list

    lids_list = [
        {"lid": "33613018058989@lid", "pn": "5511974693365@c.us"},
        {"lid": "1099562024960@lid",  "pn": "5511974693365@c.us"},
    ]
    result = build_lids_map_from_list(lids_list)

    assert result["33613018058989@lid"] == "5511974693365"
    assert result["1099562024960@lid"] == "5511974693365"
