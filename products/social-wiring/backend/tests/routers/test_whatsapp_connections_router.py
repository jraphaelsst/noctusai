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
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from noctusai_lib.integrations.whatsapp import FakeWahaClient

from app.services.whatsapp_connection_store import WhatsAppConnectionStore
from app.sqlite_client import SQLiteClient

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, user_id, label)
);
"""


@pytest.fixture
def connections_client(client, tmp_path: Path):
    """`client` + a SQLite-backed store + a Fake WAHA factory via the router's
    DI seams. Yields the auth'd client; tears the overrides down."""
    from app.main import app
    from app.routers.whatsapp_connections_router import (
        get_connection_store,
        get_waha_client_factory,
    )

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


def _create(c, *, label="Atendimento SP", base_url="https://waha.example.com", api_key="k", **extra):
    body = {"label": label, "base_url": base_url, "api_key": api_key, **extra}
    return c.post("/api/whatsapp/connections", json=body)


class TestCrud:
    def test_create_then_list(self, connections_client):
        c, _ = connections_client
        resp = _create(c, label="Vendas RJ")
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["label"] == "Vendas RJ"
        assert created["base_url"] == "https://waha.example.com"
        assert "api_key" not in created  # secret never leaves the backend

        listed = c.get("/api/whatsapp/connections")
        assert listed.status_code == 200
        assert [r["id"] for r in listed.json()] == [created["id"]]

    def test_create_requires_base_url_when_no_waha_configured(self, connections_client):
        c, _ = connections_client
        resp = c.post(
            "/api/whatsapp/connections", json={"label": "X", "api_key": "k"}
        )
        # No body base_url + default settings.waha_base_url == "" → 422.
        assert resp.status_code == 422, resp.text

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
        cid = _create(c).json()["id"]
        assert c.post(f"/api/whatsapp/connections/{cid}/start").status_code == 200
        assert fakes["default"].start_count == 1

    def test_logout(self, connections_client):
        c, fakes = connections_client
        cid = _create(c).json()["id"]
        fakes_default = c.post(f"/api/whatsapp/connections/{cid}/start")  # ensure session exists
        assert fakes_default.status_code == 200
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
