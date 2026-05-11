"""Router-level coverage for ``app.routers.condominiums``.

Closes the last Phase 3 router-test-coverage gap surfaced at Phase 0
(§5.4.8). The router is read-only and small (one endpoint), so coverage
is correspondingly tight:

  - GET /api/condominiums          → 200 + `{data: [...]}` envelope
                                     listing only ``active=True`` rows
                                     ordered by ``name``.
  - GET /api/condominiums          → 200 + `{data: []}` when no rows.
  - GET /api/condominiums          → 400 + `{detail}` when the underlying
                                     query raises.
  - Auth boundary (Pattern F adoption): missing Authorization header → 401.

Status-code-assertion rule (`KB § PATTERNS/testing.md` + Phase 0 §b.3
calibration) — every body assertion is paired with a ``status_code``
check in the same test method.
"""
from __future__ import annotations

from unittest.mock import patch

from noctusai_lib.testing import MockSupabaseClient


def _patch_condominiums_db(mock_sb):
    """`condominiums.py` does `from app.database import get_supabase_client`,
    snapshotting the symbol at import time. Patch the router's bound
    symbol directly so the route reads from this test's mock client."""
    return patch(
        "app.routers.condominiums.get_supabase_client", return_value=mock_sb
    )


def test_list_condominiums_returns_envelope_with_active_rows(client):
    """200 + `{data: [...]}` with active rows."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "condominiums",
        [
            {"id": 100, "name": "Edificio Aurora", "active": True},
            {"id": 101, "name": "Edificio Boreal", "active": True},
        ],
    )

    with _patch_condominiums_db(mock):
        resp = client.get("/api/condominiums")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    rows = body["data"]
    assert len(rows) == 2
    # Router selects only id + name (small dropdown payload).
    assert rows[0]["id"] == 100
    assert rows[0]["name"] == "Edificio Aurora"
    assert rows[1]["id"] == 101
    assert rows[1]["name"] == "Edificio Boreal"


def test_list_condominiums_returns_empty_envelope_when_no_rows(client):
    """0 active rows → still 200 + `{data: []}` — no failure."""
    mock = MockSupabaseClient()
    mock.set_table_data("condominiums", [])

    with _patch_condominiums_db(mock):
        resp = client.get("/api/condominiums")

    assert resp.status_code == 200
    assert resp.json() == {"data": []}


def test_list_condominiums_returns_400_when_query_raises(client):
    """Wrapped in try/except → underlying failure surfaces as 400 with
    `{detail}` per the router contract."""

    class _ExplodingClient:
        def table(self, _name):
            raise RuntimeError("boom")

    with _patch_condominiums_db(_ExplodingClient()):
        resp = client.get("/api/condominiums")

    assert resp.status_code == 400
    # Seed wraps HTTPException into `{"error": {"code", "message"}}`.
    body = resp.json()
    assert "error" in body
    assert "boom" in body["error"]["message"]


def test_list_condominiums_requires_auth(client):
    """Pattern F adoption: missing Authorization header → 401."""
    resp = client.raw().get("/api/condominiums")
    assert resp.status_code == 401
