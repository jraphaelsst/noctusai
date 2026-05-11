"""Tests for the seed `team` standard router — `/api/team/accept` happy path.

Scope: end-to-end exercise of the POST `/api/team/accept` endpoint through
`_create_team_router(...)`. Prior to the 2026-05-11 caller-side fix, the router
invoked `validate_invitation(db=..., schema=..., token=...)` and
`accept_invitation(db=..., schema=..., token=..., user_id=..., email=...,
password=..., name=...)` — but the domain helpers accept `(db, table: str,
token|invitation_id)` as positional args. **TypeError on first call.**

The drift survived because no integration test exercised the endpoint — only
the build-time signature-parse tests. This file closes that gap.

Test-data strategy: seed REAL invitation rows via the seed's `MockSupabaseClient`
(no monkey-patching of `noctusai_lib.domain.invitations` — per the
"no-monkey-patching-of-our-own-code" rule). The router's auth gate
(`deps.get_current_user`) is at the external boundary — `AsyncMock` is fine
there.

Status-code-assertion-rule: every body assertion is paired with a
`.status_code` assertion in the same method (defends against the
YouTube-Crawler Phase-1 false-green slip).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.routers import _create_team_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_invitation_row(
    *,
    token: str = "tok-xyz",
    status: str = "pending",
    expires_at: str | None = None,
    invitation_id: str = "inv-1",
    org_id: str = "org-1",
    email: str = "invitee@test.com",
) -> dict:
    """Build an invitation row matching `seed.invitations` shape."""
    if expires_at is None:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    return {
        "id": invitation_id,
        "org_id": org_id,
        "email": email,
        "role": "member",
        "invited_by": "u-admin",
        "token": token,
        "status": status,
        "expires_at": expires_at,
    }


@pytest.fixture
def team_app(fake_deps, fake_settings, product_name):
    """Mount the team router on a fresh FastAPI app with mock-backed deps.

    `deps._db.schema = "test"` (set by the seed conftest fixture) drives the
    router to compute `table = "test.invitations"`. We attach a
    `MockSupabaseClient` and pre-seed an invitation row so the
    /accept happy-path runs end-to-end.
    """
    mock_db = MockSupabaseClient(validate_schema=False, schema="test")
    fake_deps.get_admin_client = MagicMock(return_value=mock_db)

    app = FastAPI()
    router: APIRouter = _create_team_router(fake_deps, fake_settings, product_name)
    app.include_router(router)

    # Attach mock for per-test seeding.
    app.state.mock_db = mock_db
    return app


@pytest.fixture
def client(team_app):
    return TestClient(team_app)


# ---------------------------------------------------------------------------
# Happy-path tests — these FAIL with the pre-fix `db=, schema=, token=` kwargs
# and PASS once the router adapts to the domain signature `(db, table, token|id)`.
# ---------------------------------------------------------------------------


class TestAcceptInvitationEndpoint:
    """POST /api/team/accept end-to-end against `_create_team_router(...)`.

    Pre-fix shape (broken):
        validate_invitation(db=db, schema=schema, token=token)        # TypeError
        accept_invitation(db=db, schema=schema, token=..., user_id=..., ...)

    Post-fix shape (working):
        table = f"{schema}.invitations"
        inv = validate_invitation(db, table, payload.token)
        accept_invitation(db, table, inv["id"])

    These assertions would have raised TypeError before the fix, surfacing as
    HTTP 500. Post-fix, the happy path returns 200.
    """

    def test_accept_happy_path_returns_200(self, team_app, client):
        """Posting a valid token marks the invitation accepted and returns 200."""
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "test.invitations",
            [_make_invitation_row(token="happy-tok", invitation_id="inv-happy")],
        )

        resp = client.post("/api/team/accept", json={"token": "happy-tok"})

        # Status-code-assertion-rule: ALWAYS pair with status_code.
        # Pre-fix: TypeError inside the handler → 500. Post-fix: 200.
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}. "
            "Pre-fix the router invokes validate_invitation/accept_invitation "
            "with `db=, schema=, token=` kwargs but the domain helpers accept "
            "(db, table, token|id) positionally — TypeError surfaces as 500."
        )
        body = resp.json()
        assert "data" in body

    def test_accept_invalid_token_returns_404(self, team_app, client):
        """Unknown token → domain helper raises HTTPException(404)."""
        mock_db = team_app.state.mock_db
        # No matching row — `.single()` returns empty data.
        mock_db.set_table_data("test.invitations", [])

        resp = client.post("/api/team/accept", json={"token": "no-such-token"})

        assert resp.status_code == 404, (
            f"Expected 404 (not-found), got {resp.status_code}. Body: {resp.text}"
        )
        assert resp.json()["detail"] == "Convite nao encontrado"

    def test_accept_already_used_returns_400(self, team_app, client):
        """A non-pending invitation → domain helper raises HTTPException(400)."""
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "test.invitations",
            [
                _make_invitation_row(
                    token="already-used",
                    status="accepted",
                    invitation_id="inv-used",
                )
            ],
        )

        resp = client.post("/api/team/accept", json={"token": "already-used"})

        assert resp.status_code == 400, (
            f"Expected 400 (already-used), got {resp.status_code}. Body: {resp.text}"
        )
        assert "ja foi utilizado" in resp.json()["detail"]

    def test_accept_expired_returns_400(self, team_app, client):
        """Expired invitation → domain helper raises HTTPException(400) +
        auto-expires the row."""
        mock_db = team_app.state.mock_db
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_db.set_table_data(
            "test.invitations",
            [
                _make_invitation_row(
                    token="expired-tok",
                    expires_at=past,
                    invitation_id="inv-exp",
                )
            ],
        )

        resp = client.post("/api/team/accept", json={"token": "expired-tok"})

        assert resp.status_code == 400, (
            f"Expected 400 (expired), got {resp.status_code}. Body: {resp.text}"
        )
        assert resp.json()["detail"] == "Convite expirado"


class TestValidateInvitationEndpoint:
    """GET /api/team/accept/validate — companion endpoint also affected by
    the same caller-side kwarg drift."""

    def test_validate_happy_path_returns_200(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "test.invitations",
            [_make_invitation_row(token="valid-tok", invitation_id="inv-v")],
        )

        resp = client.get("/api/team/accept/validate", params={"token": "valid-tok"})

        # Pre-fix: TypeError → 500. Post-fix: 200.
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}"
        )
        body = resp.json()
        assert body["data"]["token"] == "valid-tok"
        assert body["data"]["status"] == "pending"

    def test_validate_invalid_returns_404(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data("test.invitations", [])

        resp = client.get("/api/team/accept/validate", params={"token": "missing"})

        assert resp.status_code == 404, (
            f"Expected 404, got {resp.status_code}. Body: {resp.text}"
        )


class TestRouterSurfaceUnchanged:
    """Guard: confirm the router still mounts the expected paths so the
    caller-side refactor didn't accidentally move routes around."""

    def test_team_router_exposes_accept_endpoints(self, team_app):
        paths = {route.path for route in team_app.router.routes if hasattr(route, "path")}
        assert "/api/team/accept" in paths
        assert "/api/team/accept/validate" in paths
