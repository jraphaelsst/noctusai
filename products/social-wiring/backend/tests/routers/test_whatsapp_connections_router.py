"""Tests for whatsapp_connections_router — per-user multi-session WAHA lines.

Drives the full API surface through two DI seams (no patching of our own
symbols or the external integration):

  - ``get_connection_store`` → a REAL SQLite-backed store (genuine CRUD
    persistence across requests + a real Fernet round-trip).
  - ``get_waha_client_factory`` → a per-session ``FakeWahaClient`` producer
    (deterministic live-ops without real HTTP).

Auth + the 503-on-config-gap path come from the shared ``client`` fixture
(MockSupabaseClient + default empty ENCRYPTION_KEY). Per
``KB § PATTERNS/di-test-seam.md`` (Class-B).

Contract v2 changes (social-waha-connect-backend):
  - Create payload shrinks to {label, api_key}.
  - ``base_url`` / ``session_name`` / ``webhook_url`` are server-derived.
  - ``session_name`` is the configured WAHA session (``"default"``) — WAHA Core
    permits only the single ``default`` session.
  - Auto ``webhook_token`` + public ``webhook_url`` built from the resolver.
  - ``set_webhook`` is called on create with the token URL.
  - New POST /api/whatsapp/webhook/{token} route.
  - GET /{id}/api-key reveals the decrypted key (owner-scoped, reveal-only).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from noctusai_lib.integrations.whatsapp import FakeWahaClient

from app.services.whatsapp_connection_store import WhatsAppConnectionStore
from app.sqlite_client import SQLiteClient

_PRODUCT_BASE = "https://social.noctusai.com"

_SCHEMA = """
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


@pytest.fixture
def connections_client(client, tmp_path: Path, override_settings, monkeypatch):
    """`client` + a SQLite-backed store + a Fake WAHA factory via the router's
    DI seams. Also configures ``waha_base_url`` via the settings DI seam and
    sets ``PRODUCT_URL_SOCIAL_WIRING`` env var so ``resolve_product_url``
    returns a deterministic value in tests. Yields (auth_client, fakes_dict);
    tears all overrides down."""
    from app.main import app
    from app.routers.whatsapp_connections_router import (
        get_connection_store,
        get_waha_client_factory,
    )

    # ── Settings: configure waha_base_url so create can resolve the server ──
    override_settings(waha_base_url="https://waha.example.com")

    # ── Product URL: deterministic via env var (no network / no DB) ──────────
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", _PRODUCT_BASE)

    db_path = tmp_path / "router_conn.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    store = WhatsAppConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(Fernet.generate_key())
    )

    fakes: dict[str, FakeWahaClient] = {}

    def fake_factory(*, base_url=None, api_key=None, session="default"):
        # One Fake per session so state (start/logout) persists across requests.
        return fakes.setdefault(session, FakeWahaClient(session=session))

    _prev_store = app.dependency_overrides.get(get_connection_store)
    _prev_factory = app.dependency_overrides.get(get_waha_client_factory)
    app.dependency_overrides[get_connection_store] = lambda: store
    app.dependency_overrides[get_waha_client_factory] = lambda: fake_factory

    yield client, fakes

    for dep, prev in (
        (get_connection_store, _prev_store),
        (get_waha_client_factory, _prev_factory),
    ):
        if prev is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = prev


def _create(c, *, label="Atendimento SP", api_key="k"):
    """Create a connection via the v2 contract: only label + api_key."""
    body = {"label": label, "api_key": api_key}
    return c.post("/api/whatsapp/connections", json=body)


class TestCrud:
    def test_create_then_list(self, connections_client):
        c, _ = connections_client
        resp = _create(c, label="Vendas RJ")
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["label"] == "Vendas RJ"
        assert "api_key" not in created  # secret never leaves the backend

        listed = c.get("/api/whatsapp/connections")
        assert listed.status_code == 200
        assert [r["id"] for r in listed.json()] == [created["id"]]

    def test_create_derives_base_url_from_config(self, connections_client):
        """base_url is set from cfg.waha_base_url, not from the request."""
        c, _ = connections_client
        resp = _create(c)
        assert resp.status_code == 201, resp.text
        assert resp.json()["base_url"] == "https://waha.example.com"

    def test_create_uses_configured_session_name(self, connections_client):
        """session_name is the configured WAHA session ("default") — WAHA Core
        permits only the single 'default' session, so every line drives it."""
        c, _ = connections_client
        resp1 = _create(c, label="Line 1")
        resp2 = _create(c, label="Line 2")
        assert resp1.status_code == 201, resp1.text
        assert resp2.status_code == 201, resp2.text

        s1 = resp1.json()["session_name"]
        s2 = resp2.json()["session_name"]
        assert s1 == "default", f"expected configured 'default' session, got {s1!r}"
        assert s2 == "default", f"expected configured 'default' session, got {s2!r}"

    def test_reveal_api_key_returns_decrypted_owner_scoped(self, connections_client):
        """GET /{id}/api-key reveals the decrypted key (the one deliberate
        secret-bearing path); a real Fernet round-trip through the store."""
        c, _ = connections_client
        created = _create(c, label="Reveal me", api_key="super-secret-key").json()
        resp = c.get(f"/api/whatsapp/connections/{created['id']}/api-key")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == created["id"]
        assert body["api_key"] == "super-secret-key"

    def test_reveal_api_key_404_for_unknown_line(self, connections_client):
        """A line the caller doesn't own (here: unknown id) is 404, never a leak."""
        import uuid

        c, _ = connections_client
        resp = c.get(f"/api/whatsapp/connections/{uuid.uuid4()}/api-key")
        assert resp.status_code == 404, resp.text

    def test_create_derives_webhook_url_from_resolver(self, connections_client):
        """webhook_url is built from resolve_product_url + /api/whatsapp/webhook/{token}."""
        c, _ = connections_client
        resp = _create(c)
        assert resp.status_code == 201, resp.text
        webhook_url = resp.json()["webhook_url"]
        assert webhook_url is not None
        assert webhook_url.startswith(f"{_PRODUCT_BASE}/api/whatsapp/webhook/"), (
            f"Expected token URL starting with {_PRODUCT_BASE}/api/whatsapp/webhook/, "
            f"got {webhook_url!r}"
        )
        # Token is a non-empty path segment after the prefix
        token_part = webhook_url.split("/api/whatsapp/webhook/")[-1]
        assert len(token_part) >= 10, "webhook token should be non-trivially long"

    def test_create_calls_set_webhook_with_token_url(self, connections_client):
        """set_webhook is invoked on create and the FakeWahaClient records it."""
        c, fakes = connections_client
        resp = _create(c)
        assert resp.status_code == 201, resp.text
        session_name = resp.json()["session_name"]
        webhook_url = resp.json()["webhook_url"]

        # The FakeWahaClient keyed by session_name should have the webhook config.
        assert session_name in fakes, (
            f"Expected fake client for session {session_name!r}; got keys {list(fakes)}"
        )
        fake = fakes[session_name]
        assert fake.webhook_config is not None, "set_webhook was not called"
        assert fake.webhook_config["url"] == webhook_url
        assert "message" in fake.webhook_config["events"]
        assert "session.status" in fake.webhook_config["events"]

    def test_create_calls_start_session(self, connections_client):
        """start_session is called on create."""
        c, fakes = connections_client
        resp = _create(c)
        assert resp.status_code == 201, resp.text
        session_name = resp.json()["session_name"]
        assert fakes[session_name].start_count == 1

    def test_update_label(self, connections_client):
        c, _ = connections_client
        cid = _create(c, label="Old").json()["id"]
        resp = c.patch(f"/api/whatsapp/connections/{cid}", json={"label": "New"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "New"

    def test_delete(self, connections_client):
        c, _ = connections_client
        cid = _create(c).json()["id"]
        assert c.delete(f"/api/whatsapp/connections/{cid}").status_code == 204
        assert c.get("/api/whatsapp/connections").json() == []

    def test_unknown_id_404(self, connections_client):
        c, _ = connections_client
        missing = "00000000-0000-4000-8000-0000000000ff"
        assert c.get(f"/api/whatsapp/connections/{missing}/status").status_code == 404
        assert c.delete(f"/api/whatsapp/connections/{missing}").status_code == 404


class TestLiveOps:
    def test_status_unpaired(self, connections_client):
        c, _ = connections_client
        cid = _create(c).json()["id"]
        resp = c.get(f"/api/whatsapp/connections/{cid}/status")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["paired"] is False
        assert body["status"] == "SCAN_QR_CODE"
        assert body["connection_id"] == cid

    def test_qr_scannable(self, connections_client):
        c, _ = connections_client
        cid = _create(c).json()["id"]
        resp = c.get(f"/api/whatsapp/connections/{cid}/qr")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["scannable"] is True
        assert body["png_base64"]

    def test_start_then_qr(self, connections_client):
        c, fakes = connections_client
        created = _create(c).json()
        cid = created["id"]
        session_name = created["session_name"]
        resp = c.post(f"/api/whatsapp/connections/{cid}/start")
        assert resp.status_code == 200
        # start_count includes the create-time call (1) + explicit /start (1)
        assert fakes[session_name].start_count == 2

    def test_logout(self, connections_client):
        c, fakes = connections_client
        created = _create(c).json()
        cid = created["id"]
        resp = c.post(f"/api/whatsapp/connections/{cid}/start")
        assert resp.status_code == 200
        resp = c.post(f"/api/whatsapp/connections/{cid}/logout")
        assert resp.status_code == 200, resp.text

    def test_webhook_persists_url(self, connections_client):
        c, _ = connections_client
        cid = _create(c).json()["id"]
        resp = c.post(
            f"/api/whatsapp/connections/{cid}/webhook",
            json={"url": "https://app/api/whatsapp/webhook"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True
        # The line remembers the last-wired webhook.
        listed = c.get("/api/whatsapp/connections").json()
        assert listed[0]["webhook_url"] == "https://app/api/whatsapp/webhook"


class TestConfigGap:
    def test_missing_encryption_key_503(self, client, override_settings):
        """No store override → the real get_connection_store path; empty
        ENCRYPTION_KEY must surface as a 503, not a 500."""
        override_settings(encryption_key="")
        resp = client.get("/api/whatsapp/connections")
        assert resp.status_code == 503, resp.text

    def test_missing_waha_base_url_503(self, connections_client, override_settings):
        """Empty waha_base_url → 503 (no silent fallback)."""
        c, _ = connections_client
        override_settings(waha_base_url="")
        resp = c.post("/api/whatsapp/connections", json={"label": "X", "api_key": "k"})
        assert resp.status_code == 503, resp.text

    def test_missing_product_url_503(self, connections_client, monkeypatch):
        """Unresolvable product URL → 503."""
        c, _ = connections_client
        # Remove the env var so resolve_product_url raises ValueError.
        monkeypatch.delenv("PRODUCT_URL_SOCIAL_WIRING", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        resp = c.post("/api/whatsapp/connections", json={"label": "X", "api_key": "k"})
        assert resp.status_code == 503, resp.text


class TestTokenWebhookRoute:
    """Token-scoped inbound webhook route tests.

    The route resolves the connection by the opaque token, then runs the
    same processing pipeline as the legacy /webhook route.

    Because the webhook route builds the store directly from settings
    (not through the connections_client DI override), we wire up a store
    with a known token directly in the DB here.
    """

    @pytest.fixture
    def token_webhook_db(self, tmp_path: Path):
        """A SQLite-backed store with one seeded row at a known token."""
        from app.services.whatsapp_connection_store import WhatsAppConnectionStore
        from app.sqlite_client import SQLiteClient
        from cryptography.fernet import Fernet
        from uuid import uuid4

        db_path = tmp_path / "wh_token.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)

        fernet = Fernet(Fernet.generate_key())
        store = WhatsAppConnectionStore(SQLiteClient(db_path), fernet=fernet)
        rec = store.create_connection(
            org_id=__import__("uuid").UUID("00000000-0000-4000-8000-000000000001"),
            user_id=__import__("uuid").UUID("00000000-0000-4000-8000-0000000000aa"),
            label="Token Test",
            base_url="https://waha.example.com",
            api_key="test-key",
            session_name="sw-aabbcc",
            webhook_url=f"{_PRODUCT_BASE}/api/whatsapp/webhook/KNOWNTOKEN",
            webhook_token="KNOWNTOKEN",
        )
        return db_path, store, rec, fernet

    def test_unknown_token_404(self, client):
        resp = client.post(
            "/api/whatsapp/webhook/totally-unknown-token-xyz",
            json={"event": "message", "session": "default", "payload": {}},
        )
        assert resp.status_code == 404, resp.text

    def test_known_token_processes_message(self, client, override_settings, token_webhook_db):
        """A valid token resolves the connection and the route returns 200.

        Injects the seeded store via the ``get_token_webhook_store`` DI seam
        (``app.dependency_overrides``) — the same override pattern the
        connections_client fixture uses for ``get_connection_store``. We do NOT
        patch the module-level factory; overriding the seam keeps the real route
        wiring exercised (no-monkey-patch-internals).
        """
        from app.main import app
        from app.routers.whatsapp_router import get_token_webhook_store

        db_path, store, rec, fernet = token_webhook_db

        _prev = app.dependency_overrides.get(get_token_webhook_store)
        app.dependency_overrides[get_token_webhook_store] = lambda: store
        try:
            resp = client.post(
                "/api/whatsapp/webhook/KNOWNTOKEN",
                json={
                    "event": "session.status",
                    "session": "sw-aabbcc",
                    "payload": {"status": "WORKING"},
                },
            )
        finally:
            if _prev is None:
                app.dependency_overrides.pop(get_token_webhook_store, None)
            else:
                app.dependency_overrides[get_token_webhook_store] = _prev
        # The route always 200-acks WAHA payloads.
        assert resp.status_code == 200, resp.text

    def test_unknown_token_no_leak(self, client):
        """Unknown token returns 404 with no information about the token space."""
        resp = client.post(
            "/api/whatsapp/webhook/notthere",
            json={"event": "message"},
        )
        assert resp.status_code == 404
        # Response body should be generic (not reference the token).
        body_text = resp.text
        assert "notthere" not in body_text

    def test_known_token_with_encryption_not_configured_404(self, client, override_settings):
        """When encryption key is missing the store can't be built; return 404
        (not 503) to avoid leaking config state to unauthenticated callers."""
        override_settings(encryption_key="")
        resp = client.post(
            "/api/whatsapp/webhook/sometoken",
            json={"event": "message"},
        )
        assert resp.status_code == 404, resp.text
