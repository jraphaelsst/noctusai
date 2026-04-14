"""
End-to-end integration tests for ERP backend team management flows.

Tests the full request lifecycle (router -> shared invitations -> response)
with mocked Supabase.  Uses the ``client`` fixture from the root conftest.py
which provides MockSupabaseClient-backed auth.

The ERP team router imports ``get_core_client`` inside function bodies via
``from app.database import get_core_client``, so we patch at
``app.database.get_core_client``.
"""
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resp(data):
    """Wrap raw data into MockSupabaseResponse (what set_sequential_responses expects)."""
    if isinstance(data, dict):
        return MockSupabaseResponse(data=[data])
    if isinstance(data, list):
        return MockSupabaseResponse(data=data)
    return MockSupabaseResponse(data=data)


def _set_responses(ms, table, responses):
    """Convenience: set sequential responses for a table, auto-wrapping raw data."""
    ms.set_sequential_responses(table, [_resp(r) for r in responses])


def _make_core_mock(owner_id="org-owner-999"):
    """Create a MockSupabaseClient simulating the core (public schema) client."""
    core = MockSupabaseClient()
    core.set_table_data("organizations", [
        {"id": "test-org-123", "nome": "Test Org", "owner_id": owner_id},
    ])
    return core


# ═══════════════════════════════════════════════════════════════════════════
# Invitation Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestERPInvitationLifecycle:
    """Test invite -> validate -> accept flow for ERP team."""

    @patch("noctusai_shared.email_templates.send_product_invitation_email", MagicMock())
    @patch("app.database.get_core_client", return_value=_make_core_mock())
    def test_invite_creates_invitation(self, mock_core, client):
        """POST /api/team/invite -> creates invitation record."""
        ms = client.mock_supabase

        # _require_erp_admin: user_roles check (user is admin)
        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])
        # existing email check on profiles
        _set_responses(ms, "profiles", [
            [],  # no existing member
        ])
        # create_invitation: pending check + insert
        _set_responses(ms, "invitations", [
            [],  # no pending duplicates
            [{"id": "inv-1", "org_id": "test-org-123", "email": "new@test.com",
              "role": "corretor", "token": "tok-abc", "status": "pending",
              "invited_by": "test-user-123"}],
        ])

        resp = client.post("/api/team/invite", json={
            "email": "new@test.com",
            "role": "corretor",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == "new@test.com"
        assert data["role"] == "corretor"

    @patch("noctusai_shared.email_templates.send_product_invitation_email", MagicMock())
    @patch("app.database.get_core_client", return_value=_make_core_mock())
    def test_duplicate_invite_returns_409(self, mock_core, client):
        """POST /api/team/invite -> 409 if email already has pending invite."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])
        _set_responses(ms, "profiles", [
            [],
        ])
        # create_invitation: pending check -> found existing
        _set_responses(ms, "invitations", [
            [{"id": "inv-existing"}],
        ])

        resp = client.post("/api/team/invite", json={
            "email": "dup@test.com",
            "role": "corretor",
        })
        assert resp.status_code == 409

    def test_cancel_invitation(self, client):
        """DELETE /api/team/invitations/{id} -> cancels pending invitation."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])
        # cancel_invitation: select check + update
        _set_responses(ms, "invitations", [
            {"id": "inv-1", "status": "pending"},
            {"id": "inv-1", "status": "canceled"},
        ])

        resp = client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_validate_invitation_endpoint(self, client):
        """GET /api/team/accept/validate?token=x -> returns email + role."""
        ms = client.mock_supabase

        invite_data = {
            "id": "inv-val-1",
            "org_id": "test-org-123",
            "email": "validate@test.com",
            "role": "coordenador",
            "status": "pending",
            "token": "val-tok-1",
            "expires_at": "2099-12-31T23:59:59+00:00",
            "invited_by": "admin-1",
        }

        _set_responses(ms, "invitations", [
            invite_data,
        ])

        core_mock = _make_core_mock()
        core_mock.set_table_data("organizations", [
            {"id": "test-org-123", "nome": "Imobiliaria XYZ"},
        ])

        with patch("app.database.get_core_client", return_value=core_mock):
            resp = client.get("/api/team/accept/validate?token=val-tok-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "validate@test.com"
        assert body["role"] == "coordenador"
        assert body["role_label"] == "Coordenador"

    def test_accept_invitation_creates_profile(self, client):
        """POST /api/team/accept -> creates auth user + profile + user_roles."""
        ms = client.mock_supabase

        invite_data = {
            "id": "inv-acc-1",
            "org_id": "test-org-123",
            "email": "newuser@test.com",
            "role": "corretor",
            "status": "pending",
            "token": "acc-tok-1",
            "expires_at": "2099-12-31T23:59:59+00:00",
            "invited_by": "admin-1",
        }

        # validate_invitation + accept_invitation
        _set_responses(ms, "invitations", [
            invite_data,
            {"id": "inv-acc-1", "status": "accepted"},
        ])
        # profiles insert
        _set_responses(ms, "profiles", [
            [{"id": "new-auth-user-id", "nome": "Joao Silva",
              "email": "newuser@test.com", "org_id": "test-org-123"}],
        ])
        # user_roles insert
        _set_responses(ms, "user_roles", [
            [{"user_id": "new-auth-user-id", "role": "corretor"}],
        ])

        # Mock auth.admin.create_user
        mock_auth_user = MagicMock()
        mock_auth_user.user.id = "new-auth-user-id"
        ms.auth.admin.create_user = MagicMock(return_value=mock_auth_user)

        resp = client.post("/api/team/accept", json={
            "token": "acc-tok-1",
            "nome": "joao silva",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "new-auth-user-id"
        assert data["email"] == "newuser@test.com"
        assert data["nome"] == "Joao Silva"  # capitalized
        assert data["role"] == "corretor"

        # Verify auth user was created with correct metadata
        ms.auth.admin.create_user.assert_called_once()
        create_args = ms.auth.admin.create_user.call_args[0][0]
        assert create_args["email"] == "newuser@test.com"
        assert create_args["user_metadata"]["org_id"] == "test-org-123"


# ═══════════════════════════════════════════════════════════════════════════
# Team Listing
# ═══════════════════════════════════════════════════════════════════════════


class TestERPTeamListing:
    """Test team member listing."""

    def test_list_members_with_roles(self, client):
        """GET /api/team -> returns members enriched with roles."""
        ms = client.mock_supabase

        _set_responses(ms, "profiles", [
            [
                {"id": "u-1", "nome": "Alice", "email": "alice@test.com",
                 "telefone": None, "cargo": None, "avatar_url": None,
                 "created_at": "2026-01-01"},
                {"id": "u-2", "nome": "Bob", "email": "bob@test.com",
                 "telefone": None, "cargo": None, "avatar_url": None,
                 "created_at": "2026-01-02"},
            ],
        ])
        _set_responses(ms, "user_roles", [
            [
                {"user_id": "u-1", "role": "admin"},
                {"user_id": "u-2", "role": "corretor"},
            ],
        ])

        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

        role_map = {m["id"]: m["role"] for m in data}
        assert role_map["u-1"] == "admin"
        assert role_map["u-2"] == "corretor"


# ═══════════════════════════════════════════════════════════════════════════
# Role Change
# ═══════════════════════════════════════════════════════════════════════════


class TestERPRoleChange:
    """Test changing a member's ERP role."""

    def test_change_member_role(self, client):
        """PATCH /api/team/{user_id}/role -> role updated."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],       # admin check for caller
            [{"id": "ur-1"}],           # existing_role check for target
            [{"user_id": "target-1", "role": "coordenador"}],  # update result
        ])
        _set_responses(ms, "profiles", [
            [{"id": "target-1", "nome": "Target User"}],
        ])

        resp = client.patch("/api/team/target-1/role", json={"role": "coordenador"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "coordenador"

    def test_cannot_change_own_role(self, client):
        """PATCH /api/team/{self}/role -> 400."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])

        # Get the actual user ID from the mock user
        user_resp = ms.auth.get_user("any")
        user_id = str(user_resp.user.id)

        resp = client.patch(f"/api/team/{user_id}/role", json={"role": "coordenador"})
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "proprio" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Remove Member
# ═══════════════════════════════════════════════════════════════════════════


class TestERPRemoveMember:
    """Test removing a member from the ERP organization."""

    @patch("app.database.get_core_client")
    def test_remove_member(self, mock_core_factory, client):
        """DELETE /api/team/{user_id} -> member removed."""
        ms = client.mock_supabase

        core_mock = _make_core_mock(owner_id="someone-else")
        mock_core_factory.return_value = core_mock

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],  # admin check
            [],  # delete user_roles
        ])
        _set_responses(ms, "profiles", [
            [{"id": "remove-me", "nome": "Removable", "email": "rm@test.com",
              "org_id": "test-org-123"}],
            [],  # delete result
        ])

        resp = client.delete("/api/team/remove-me")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_cannot_remove_self(self, client):
        """DELETE /api/team/{self} -> 400."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])

        user_resp = ms.auth.get_user("any")
        user_id = str(user_resp.user.id)

        resp = client.delete(f"/api/team/{user_id}")
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "si mesmo" in msg.lower()

    @patch("app.database.get_core_client")
    def test_cannot_remove_org_owner(self, mock_core_factory, client):
        """DELETE /api/team/{owner_id} -> 400 (org owner protected)."""
        ms = client.mock_supabase

        core_mock = _make_core_mock(owner_id="owner-user")
        mock_core_factory.return_value = core_mock

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])
        _set_responses(ms, "profiles", [
            [{"id": "owner-user", "nome": "Owner", "email": "owner@test.com",
              "org_id": "test-org-123"}],
        ])

        resp = client.delete("/api/team/owner-user")
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "proprietario" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Invitations Listing
# ═══════════════════════════════════════════════════════════════════════════


class TestERPInvitationsListing:
    """Test listing pending invitations."""

    def test_list_invitations(self, client):
        """GET /api/team/invitations -> returns pending invitations."""
        ms = client.mock_supabase

        _set_responses(ms, "user_roles", [
            [{"role": "admin"}],
        ])

        invites = [
            {"id": "i-1", "email": "a@test.com", "role": "corretor", "status": "pending",
             "invited_by": "admin-1", "expires_at": "2099-12-31", "created_at": "2026-04-01"},
            {"id": "i-2", "email": "b@test.com", "role": "admin", "status": "pending",
             "invited_by": "admin-1", "expires_at": "2099-12-31", "created_at": "2026-04-02"},
        ]

        _set_responses(ms, "invitations", [
            invites,
        ])

        resp = client.get("/api/team/invitations")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
