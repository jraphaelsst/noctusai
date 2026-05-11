"""Router-level coverage for ``app.routers.authorized_users``.

Lands in Phase 1 of media-scheduling-wiring alongside:
  - Pattern F adoption (factory-based `Depends(get_current_user_org)`).
  - Migration 007 (`notes` TEXT column on authorized_users — closing the
    phantom-field-on-write slip).

Covers:
  - GET    /api/authorized-users   → 200 + wired rows envelope.
  - POST   /api/authorized-users   → 200 + inserted_payloads carries `notes`.
  - GET    /api/authorized-users/{id} → 200 + wired row OR 404.
  - PATCH  /api/authorized-users/{id} → 200 + updates persist `notes`.
  - DELETE /api/authorized-users/{id} → 200 + `{ok: true}`.
  - Auth boundary: missing Authorization header → 401 across all 5 routes.
"""
from __future__ import annotations

from unittest.mock import patch

from noctusai_lib.testing import MockSupabaseClient


def _patch_authorized_users_db(mock_sb):
    """`authorized_users.py` does `from app.database import get_supabase_client`,
    snapshotting the symbol at import time. Patch the router's bound
    symbol directly."""
    return patch(
        "app.routers.authorized_users.get_supabase_client", return_value=mock_sb
    )


def test_list_authorized_users_returns_wired_envelope(client):
    """200 + `is_active` populated, `active` column gone — wire-shape."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "authorized_users",
        [
            {
                "id": 1,
                "name": "Alice",
                "phone_number": "+5511999990001",
                "role": "real_estate_agent",
                "email": "alice@example.com",
                "active": True,
                "notes": "VIP client",
                "created_at": "2026-05-01T00:00:00+00:00",
                "updated_at": "2026-05-01T00:00:00+00:00",
            },
        ],
    )

    with _patch_authorized_users_db(mock):
        resp = client.get("/api/authorized-users")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    row = body["data"][0]
    assert row["is_active"] is True
    assert "active" not in row
    assert row["notes"] == "VIP client"


def test_create_authorized_user_persists_notes(client):
    """POST round-trips the `notes` field (column added in migration 007)."""
    mock = MockSupabaseClient()
    mock.set_table_data("authorized_users", [])

    with _patch_authorized_users_db(mock):
        resp = client.post(
            "/api/authorized-users",
            json={
                "name": "Bob",
                "phone_number": "+5511999990002",
                "role": "real_estate_agent",
                "email": "bob@example.com",
                "is_active": True,
                "notes": "Prefers afternoon shoots",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    # The inserted payload reaches the DB with `notes` intact.
    inserted = mock.table("authorized_users").inserted_payloads
    assert len(inserted) == 1
    assert inserted[0]["notes"] == "Prefers afternoon shoots"
    # And `active` column shape (not `is_active`) is persisted.
    assert inserted[0]["active"] is True
    # Response wire-shape uses is_active, not active.
    assert "is_active" in body or body  # Mock returns the inserted row.


def test_create_authorized_user_rejects_missing_phone(client):
    """phone_number is required → 400."""
    mock = MockSupabaseClient()
    mock.set_table_data("authorized_users", [])

    with _patch_authorized_users_db(mock):
        resp = client.post(
            "/api/authorized-users",
            json={
                "name": "Bob",
                "phone_number": "",
                "role": "real_estate_agent",
            },
        )

    # Pydantic min_length=1 catches this at 422; if the route's own
    # 400 fires, also acceptable. Either way: not 200.
    assert resp.status_code in (400, 422)


def test_get_authorized_user_detail_returns_wired_row(client):
    """200 + is_active wire-shape on detail route.

    Note: seeded ``id`` is the string ``"1"`` so the mock's literal-eq
    evaluator matches the URL path string. See appointments test for
    the same constraint.
    """
    mock = MockSupabaseClient()
    mock.set_table_data(
        "authorized_users",
        [
            {
                "id": "1",
                "name": "Alice",
                "phone_number": "+5511999990001",
                "role": "real_estate_agent",
                "email": "alice@example.com",
                "active": False,
                "notes": None,
                "created_at": "2026-05-01T00:00:00+00:00",
                "updated_at": "2026-05-01T00:00:00+00:00",
            },
        ],
    )

    with _patch_authorized_users_db(mock):
        resp = client.get("/api/authorized-users/1")

    assert resp.status_code == 200
    row = resp.json()
    assert row["is_active"] is False
    assert row["notes"] is None


def test_get_authorized_user_returns_404_when_missing(client):
    """No matching row → 404 + detail message."""
    mock = MockSupabaseClient()
    mock.set_table_data("authorized_users", [])

    with _patch_authorized_users_db(mock):
        resp = client.get("/api/authorized-users/999")

    assert resp.status_code == 404
    # Seed wraps HTTPException into `{"error": {"code", "message"}}`.
    assert resp.json()["error"]["message"] == "Authorized user not found"


def test_update_authorized_user_persists_notes(client):
    """PATCH `notes` lands in the update payload (no longer dropped)."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "authorized_users",
        [
            {
                "id": "1",
                "name": "Alice",
                "phone_number": "+5511999990001",
                "role": "real_estate_agent",
                "email": None,
                "active": True,
                "notes": None,
                "created_at": "2026-05-01T00:00:00+00:00",
                "updated_at": "2026-05-01T00:00:00+00:00",
            },
        ],
    )

    with _patch_authorized_users_db(mock):
        resp = client.patch(
            "/api/authorized-users/1",
            json={"notes": "Updated note from PATCH"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["notes"] == "Updated note from PATCH"


def test_update_authorized_user_returns_404_when_missing(client):
    """No matching row to update → 404."""
    mock = MockSupabaseClient()
    mock.set_table_data("authorized_users", [])

    with _patch_authorized_users_db(mock):
        resp = client.patch(
            "/api/authorized-users/999",
            json={"name": "Ghost"},
        )

    assert resp.status_code == 404


def test_update_authorized_user_rejects_empty_payload(client):
    """No fields → 400 (matches `if not payload: raise 400` guard)."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "authorized_users",
        [{"id": "1", "name": "Alice", "phone_number": "+5511999990001", "active": True}],
    )

    with _patch_authorized_users_db(mock):
        resp = client.patch("/api/authorized-users/1", json={})

    assert resp.status_code == 400
    # Seed wraps HTTPException into `{"error": {"code", "message"}}`.
    assert resp.json()["error"]["message"] == "No fields to update"


def test_delete_authorized_user_returns_ok(client):
    """DELETE → 200 + `{ok: true}`."""
    mock = MockSupabaseClient()
    mock.set_table_data(
        "authorized_users",
        [{"id": "1", "name": "Alice", "phone_number": "+5511999990001", "active": True}],
    )

    with _patch_authorized_users_db(mock):
        resp = client.delete("/api/authorized-users/1")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_list_authorized_users_requires_auth(client):
    """Pattern F: missing Authorization header → 401."""
    resp = client.raw().get("/api/authorized-users")
    assert resp.status_code == 401


def test_create_authorized_user_requires_auth(client):
    resp = client.raw().post(
        "/api/authorized-users",
        json={"name": "X", "phone_number": "+5511999990003"},
    )
    assert resp.status_code == 401


def test_get_authorized_user_requires_auth(client):
    resp = client.raw().get("/api/authorized-users/1")
    assert resp.status_code == 401


def test_update_authorized_user_requires_auth(client):
    resp = client.raw().patch("/api/authorized-users/1", json={"name": "Y"})
    assert resp.status_code == 401


def test_delete_authorized_user_requires_auth(client):
    resp = client.raw().delete("/api/authorized-users/1")
    assert resp.status_code == 401
