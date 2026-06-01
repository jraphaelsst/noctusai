"""Tests for the clients_router — /api/clients/*.

Tests use the DI seam (app.dependency_overrides[get_client_service]) with a
SQLite-backed ClientService (real CRUD). No monkey-patching per
KB § PATTERNS/di-test-seam.md.

Coverage:
  - CRUD round-trips (list / create / update / delete)
  - 401 on missing Authorization — strict == 401 per auth-boundary rule
  - 404 on nonexistent
  - Org isolation (org A cannot see org B's clients via list)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.services.clients_service import ClientService, build_client_service
from app.sqlite_client import SQLiteClient

_ORG_A = "00000000-0000-4000-8000-000000000001"
_ORG_B = "00000000-0000-4000-8000-000000000002"

_CLIENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'real_estate_agent',
    notes       TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, slug)
);
"""


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sqlite_clients_db(tmp_path: Path) -> SQLiteClient:
    db_path = tmp_path / "clients.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_CLIENT_SCHEMA)
    return SQLiteClient(db_path)


@pytest.fixture
def client_svc(sqlite_clients_db: SQLiteClient) -> ClientService:
    return build_client_service(sqlite_clients_db)


@pytest.fixture
def http_client(client_svc):
    """TestClient with client service DI seam wired to SQLite."""
    from unittest.mock import MagicMock, patch
    from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse

    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=_ORG_A))
    )

    from app.routers.clients_router import get_client_service
    from noctusai_lib.testing import bind_consent_module_to_mock

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)

        app.dependency_overrides[get_client_service] = lambda: client_svc
        tc = TestClient(app, raise_server_exceptions=True)
        yield tc
        app.dependency_overrides.pop(get_client_service, None)


def _auth():
    return {"Authorization": "Bearer test-token"}


def _make_client(http_client, *, slug="agent-x", name="Agent X", kind="real_estate_agent"):
    body = {"slug": slug, "name": name, "kind": kind}
    resp = http_client.post("/api/clients", json=body, headers=_auth())
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── Auth boundary — strict 401 ───────────────────────────────────────────────

class TestAuth:
    def test_list_requires_auth(self, http_client):
        resp = http_client.get("/api/clients")
        assert resp.status_code == 401

    def test_create_requires_auth(self, http_client):
        resp = http_client.post("/api/clients", json={"slug": "x", "name": "X"})
        assert resp.status_code == 401

    def test_update_requires_auth(self, http_client):
        resp = http_client.patch(f"/api/clients/{uuid4()}", json={"name": "Y"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, http_client):
        resp = http_client.delete(f"/api/clients/{uuid4()}")
        assert resp.status_code == 401


# ─── CRUD round-trips ─────────────────────────────────────────────────────────

class TestCRUD:
    def test_list_empty(self, http_client):
        resp = http_client.get("/api/clients", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_returns_201(self, http_client):
        data = _make_client(http_client)
        assert data["slug"] == "agent-x"
        assert data["name"] == "Agent X"
        assert "id" in data
        assert "org_id" in data

    def test_list_one(self, http_client):
        _make_client(http_client)
        resp = http_client.get("/api/clients", headers=_auth())
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_create_forbidden_fields_422(self, http_client):
        """extra='forbid' on the create model."""
        resp = http_client.post(
            "/api/clients",
            json={"slug": "x", "name": "X", "unknown_field": True},
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_update_name(self, http_client):
        data = _make_client(http_client)
        resp = http_client.patch(
            f"/api/clients/{data['id']}",
            json={"name": "Updated Agent"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Agent"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/clients/{uuid4()}",
            json={"name": "X"},
            headers=_auth(),
        )
        assert resp.status_code == 404

    def test_delete_existing(self, http_client):
        data = _make_client(http_client)
        resp = http_client.delete(
            f"/api/clients/{data['id']}", headers=_auth()
        )
        assert resp.status_code == 204

    def test_delete_nonexistent_404(self, http_client):
        resp = http_client.delete(
            f"/api/clients/{uuid4()}", headers=_auth()
        )
        assert resp.status_code == 404

    def test_list_only_own_org(self, http_client, client_svc):
        """Clients created for _ORG_B must NOT appear in org A's list."""
        from uuid import UUID
        client_svc.create_client(
            org_id=UUID(_ORG_B), slug="b-client", name="B Client"
        )
        resp = http_client.get("/api/clients", headers=_auth())
        assert resp.status_code == 200
        slugs = {c["slug"] for c in resp.json()}
        assert "b-client" not in slugs
