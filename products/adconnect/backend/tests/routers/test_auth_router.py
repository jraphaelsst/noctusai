"""
Tests for the AdConnect auth router (Phase 1 of adconnect-mvp-implementation).

Phase 1 retired the custom-JWT scaffold (`/login` + bcrypt). The router
now exposes:
  - GET  /api/auth/me                         — dict-shape projection
  - POST /api/auth/accept-distributor-invite  — invitation acceptance flow

NOTE on path prefixes: the AdConnect domain routers in `main.py` do NOT
mount under `/api/...` like the seed's standard routers do — main.py
sets `router.prefix = "/auth"` after construction but FastAPI's
`include_router(...)` doesn't honor that re-assignment, so domain routes
land at the bare path the route declared. This mismatch is pre-existing
and out of scope for Phase 1 (lands as an Improvement for Phase 2 where
the routers get rewritten). Tests below use the actual mounted paths.

These tests use the existing `client` fixture from `tests/conftest.py`,
which patches the seed framework's database module to return a
`MockSupabaseClient` with a `MockUser(org_id="test-org-123")`. We only
exercise router-level behavior; service-level branching (LGPD flagging,
distributor-membership joins) lives in service tests under Phase 1+.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------


class TestAuthMe:
    def test_me_requires_auth(self, client):
        """No auth header -> 401."""
        resp = client.raw().get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_returns_dict_shape(self, client):
        """Authed call returns the legacy projection: id/email/role/distributorId."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"id", "email", "role", "distributorId"}
        # MockUser default id + email
        assert body["id"] == "test-user-123"
        assert body["email"] == "test@example.com"


# ---------------------------------------------------------------------------
# /api/auth/accept-distributor-invite
# ---------------------------------------------------------------------------

DIST_ID = "00000000-0000-0000-0000-000000000d01"
ORG_ID = "test-org-123"
TOKEN = "tok_pending_001"


def _future_iso():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")


def _past_iso():
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")


class TestAcceptDistributorInvite:
    def test_unauth_rejected(self, client):
        resp = client.raw().post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID},
        )
        assert resp.status_code == 401

    def test_token_not_found_returns_404(self, client):
        client._mock_supabase.set_table_data("invitations", [])
        client._mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_ID, "org_id": ORG_ID}],
        )
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID},
        )
        assert resp.status_code == 404
        # The seed wraps HTTPException detail into {error: {code, message}}.
        body = resp.json()
        message = body.get("error", {}).get("message") or body.get("detail", "")
        assert "convite" in message.lower()

    def test_already_accepted_token_returns_410(self, client):
        client._mock_supabase.set_table_data(
            "invitations",
            [{
                "id": "inv-1",
                "org_id": ORG_ID,
                "token": TOKEN,
                "status": "accepted",
                "expires_at": _future_iso(),
            }],
        )
        client._mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_ID, "org_id": ORG_ID}],
        )
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID},
        )
        assert resp.status_code == 410

    def test_expired_token_returns_410(self, client):
        client._mock_supabase.set_table_data(
            "invitations",
            [{
                "id": "inv-2",
                "org_id": ORG_ID,
                "token": TOKEN,
                "status": "pending",
                "expires_at": _past_iso(),
            }],
        )
        client._mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_ID, "org_id": ORG_ID}],
        )
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID},
        )
        assert resp.status_code == 410

    def test_distributor_not_in_invitation_org_returns_403(self, client):
        client._mock_supabase.set_table_data(
            "invitations",
            [{
                "id": "inv-3",
                "org_id": ORG_ID,
                "token": TOKEN,
                "status": "pending",
                "expires_at": _future_iso(),
            }],
        )
        client._mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_ID, "org_id": "other-org"}],
        )
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID},
        )
        assert resp.status_code == 403

    def test_happy_path_creates_membership(self, client):
        """Valid pending token + org-matching distributor -> 201 + membership row."""
        client._mock_supabase.set_table_data(
            "invitations",
            [{
                "id": "inv-4",
                "org_id": ORG_ID,
                "token": TOKEN,
                "status": "pending",
                "expires_at": _future_iso(),
            }],
        )
        client._mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_ID, "org_id": ORG_ID}],
        )
        client._mock_supabase.set_table_data(
            "distributor_memberships",
            {"id": "mem-1", "user_id": "test-user-123",
             "distributor_id": DIST_ID, "role": "distributor_member"},
        )
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID,
                  "role": "distributor_member"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["distributor_id"] == DIST_ID
        assert body["user_id"] == "test-user-123"
        # MockSupabaseClient tracks insert payloads.
        memberships_table = client._mock_supabase.table("distributor_memberships")
        assert any(
            p.get("distributor_id") == DIST_ID
            and p.get("user_id") == "test-user-123"
            and p.get("role") == "distributor_member"
            for p in memberships_table.inserted_payloads
        )

    def test_invalid_role_rejected_by_pydantic(self, client):
        resp = client.post(
            "/api/auth/accept-distributor-invite",
            json={"token": TOKEN, "distributor_id": DIST_ID,
                  "role": "GOD_MODE"},
        )
        assert resp.status_code == 422
