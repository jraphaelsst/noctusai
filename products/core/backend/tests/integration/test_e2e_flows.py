"""
End-to-end integration tests for Core backend flows.

Tests the full request lifecycle (router -> service -> response) with mocked
Supabase.  Uses the ``client`` and ``admin_client`` fixtures from the root
conftest.py which provide MockSupabaseClient-backed auth.

Team management endpoints require ``team:manage`` / ``team:read`` permissions,
so they use ``admin_client`` (whose ``check_permission`` returns True).
SSO endpoints are open or use standard auth, so they use ``client``.
"""
import pytest
from unittest.mock import MagicMock


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_link_response(email_otp="123456"):
    """Build a mock generate_link response with a nested .properties.email_otp."""
    link = MagicMock()
    link.properties.email_otp = email_otp
    return link


def _mock_session(access_token="new-access-tok", refresh_token="new-refresh-tok",
                  user_id="test-user-123", email="test@example.com"):
    """Build a mock verify_otp response with a nested .session."""
    resp = MagicMock()
    resp.session.access_token = access_token
    resp.session.refresh_token = refresh_token
    resp.user.id = user_id
    resp.user.email = email
    return resp


def _create_sso_token(user_id="test-user-123", org_id="org-1",
                      product_slug="erp-imobiliario", email="test@example.com",
                      role="user", org_role="member"):
    from app.dependencies import create_sso_token
    return create_sso_token(
        user_id=user_id, org_id=org_id, product_slug=product_slug,
        email=email, role=role, org_role=org_role,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SSO Flows
# ═══════════════════════════════════════════════════════════════════════════


class TestSSOTokenFlow:
    """Test SSO token generation and exchange."""

    def test_sso_generate_token_includes_org_role(self, client):
        """POST /api/sso/token -> token encodes org_role from noctus_users."""
        ms = client.mock_supabase

        # noctus_users profile lookup (for generate_sso_token)
        ms.set_table_data("noctus_users", [
            {"id": "test-user-123", "org_id": "org-1", "role": "user", "org_role": "admin"},
        ])
        # products lookup
        ms.set_table_data("products", [
            {"id": "prod-1", "slug": "erp-imobiliario"},
        ])
        # licenses lookup (check_org_license)
        ms.set_table_data("licenses", [
            {"id": "lic-1", "org_id": "org-1", "product_id": "prod-1",
             "status": "active", "fim": None},
        ])

        resp = client.post("/api/sso/token", json={"product_slug": "erp-imobiliario"})
        assert resp.status_code == 200
        data = resp.json()
        assert "sso_token" in data
        assert data["product_slug"] == "erp-imobiliario"

        # Decode the token to verify org_role is embedded
        import jwt as pyjwt
        from app.config import settings
        from noctusai_lib.api.auth import SSO_AUDIENCE, SSO_ISSUER
        payload = pyjwt.decode(
            data["sso_token"], settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=SSO_AUDIENCE, issuer=SSO_ISSUER,
        )
        assert payload["org_role"] == "admin"
        assert payload["org_id"] == "org-1"
        assert payload["type"] == "sso"

    def test_sso_session_exchange_syncs_metadata(self, client):
        """POST /api/sso/session -> exchanges token for Supabase session."""
        ms = client.mock_supabase
        sso_token = _create_sso_token()

        # Mock supabase_admin auth methods
        ms.auth.admin.update_user_by_id = MagicMock()
        ms.auth.admin.generate_link = MagicMock(return_value=_mock_link_response())
        ms.auth.verify_otp = MagicMock(return_value=_mock_session())

        # Org / subscription / license enrichment queries
        ms.set_table_responses("organizations", [
            {"id": "org-1", "nome": "Test Corp", "logo_url": None},
        ])
        ms.set_table_responses("subscriptions", [[]])
        ms.set_table_responses("products", [[]])

        resp = client.post("/api/sso/session", json={"token": sso_token})
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "new-access-tok"
        assert body["refresh_token"] == "new-refresh-tok"
        assert body["email"] == "test@example.com"

        # Verify metadata sync was called
        ms.auth.admin.update_user_by_id.assert_called_once()

    def test_sso_admin_user_gets_admin_role_in_metadata(self, client):
        """Admin user (noctus_role=admin) -> SSO session -> metadata has noctus_role=admin."""
        ms = client.mock_supabase
        sso_token = _create_sso_token(
            user_id="admin-user-456", email="admin@example.com",
            role="admin", org_role="admin",
        )

        ms.auth.admin.update_user_by_id = MagicMock()
        ms.auth.admin.generate_link = MagicMock(return_value=_mock_link_response())
        ms.auth.verify_otp = MagicMock(return_value=_mock_session(
            user_id="admin-user-456", email="admin@example.com"
        ))

        ms.set_table_responses("organizations", [
            {"id": "org-1", "nome": "Admin Corp", "logo_url": None},
        ])
        ms.set_table_responses("subscriptions", [[]])
        ms.set_table_responses("products", [[]])

        resp = client.post("/api/sso/session", json={"token": sso_token})
        assert resp.status_code == 200

        # Verify the metadata update includes noctus_role=admin
        call_args = ms.auth.admin.update_user_by_id.call_args
        metadata = call_args[1]["user_metadata"] if "user_metadata" in (call_args[1] or {}) else call_args[0][1]["user_metadata"]
        assert metadata["noctus_role"] == "admin"

    def test_sso_org_owner_gets_owner_metadata(self, client):
        """Owner user (org_role=owner) -> SSO session -> metadata has org_role=owner."""
        ms = client.mock_supabase
        sso_token = _create_sso_token(
            user_id="owner-user-789", email="owner@example.com",
            org_role="owner",
        )

        ms.auth.admin.update_user_by_id = MagicMock()
        ms.auth.admin.generate_link = MagicMock(return_value=_mock_link_response())
        ms.auth.verify_otp = MagicMock(return_value=_mock_session(
            user_id="owner-user-789", email="owner@example.com"
        ))
        ms.set_table_responses("organizations", [
            {"id": "org-1", "nome": "Owner Corp", "logo_url": None},
        ])
        ms.set_table_responses("subscriptions", [[]])
        ms.set_table_responses("products", [[]])

        resp = client.post("/api/sso/session", json={"token": sso_token})
        assert resp.status_code == 200

        call_args = ms.auth.admin.update_user_by_id.call_args
        metadata = call_args[1]["user_metadata"] if "user_metadata" in (call_args[1] or {}) else call_args[0][1]["user_metadata"]
        assert metadata["org_role"] == "owner"
        assert metadata["org_id"] == "org-1"

    def test_sso_validate_returns_payload(self, client):
        """POST /api/sso/validate -> returns decoded token fields."""
        sso_token = _create_sso_token(
            user_id="u-1", org_id="o-1", product_slug="pf",
            email="val@test.com",
        )

        resp = client.post("/api/sso/validate", json={"token": sso_token})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["user_id"] == "u-1"
        assert body["org_id"] == "o-1"
        assert body["email"] == "val@test.com"


# ═══════════════════════════════════════════════════════════════════════════
# Invitation Lifecycle (uses admin_client — team endpoints require permissions)
# ═══════════════════════════════════════════════════════════════════════════


class TestInvitationLifecycle:
    """Test the full invite -> list -> cancel flow via team router."""

    def test_invite_list_cancel(self, admin_client):
        """POST invite -> GET invitations -> DELETE invitation."""
        ms = admin_client.mock_supabase

        invite_record = {
            "id": "inv-1",
            "org_id": "test-org-123",
            "email": "new@example.com",
            "role": "member",
            "invited_by": "admin-user-456",
            "token": "abc123",
            "status": "pending",
        }

        # --- Step 1: Invite ---
        ms.set_table_responses("noctus_users", [
            # _get_user_profile
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
            # existing email check -> empty
            [],
            # audit service lookups (best-effort, may fail)
            {"id": "admin-user-456", "org_id": "test-org-123"},
            {"id": "admin-user-456"},
            # email: inviter name lookup
            {"nome": "Admin User"},
        ])
        ms.set_table_responses("roles", [
            [{"id": "role-1", "slug": "member"}],
        ])
        ms.set_table_responses("invitations", [
            [],  # no pending duplicates
            invite_record,  # insert result
        ])
        ms.set_table_data("organizations", [{"id": "test-org-123", "nome": "Test Corp"}])
        ms.set_table_data("audit_logs", [])
        ms.set_table_data("notifications", [])
        ms.set_table_data("webhook_endpoints", [])

        resp = admin_client.post("/api/team/invite", json={
            "email": "new@example.com", "role": "member",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "new@example.com"

        # --- Step 2: List invitations ---
        ms.set_table_responses("noctus_users", [
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
        ])
        ms.set_table_responses("invitations", [
            [invite_record],
        ])

        resp = admin_client.get("/api/team/invitations")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

        # --- Step 3: Cancel invitation ---
        ms.set_table_responses("noctus_users", [
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
        ])
        ms.set_table_responses("invitations", [
            {"id": "inv-1", "status": "pending"},  # cancel_invitation select
            {"id": "inv-1", "status": "canceled"},  # cancel_invitation update
        ])

        resp = admin_client.delete("/api/team/invitations/inv-1")
        assert resp.status_code == 200
        assert "cancelado" in resp.json()["message"].lower()


class TestInvitationAccept:
    """Test invitation acceptance flow."""

    def test_accept_invitation_marks_accepted(self, client):
        """POST /api/team/accept-invite -> invitation status = accepted."""
        ms = client.mock_supabase

        invite_record = {
            "id": "inv-2",
            "org_id": "org-accept",
            "email": "accept@example.com",
            "role": "member",
            "status": "pending",
            "token": "accept-token-123",
            "invited_by": "admin-1",
            "expires_at": "2099-12-31T23:59:59+00:00",
        }

        ms.set_table_responses("invitations", [
            invite_record,  # validate_invitation
            {"id": "inv-2", "status": "accepted"},  # mark_accepted
        ])
        ms.set_table_responses("noctus_users", [
            {"id": "test-user-123", "org_id": None},  # existing profile, no org
            {"id": "test-user-123", "org_id": "org-accept", "org_role": "member"},  # update
        ])

        resp = client.post("/api/team/accept-invite", json={
            "token": "accept-token-123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["org_id"] == "org-accept"
        assert body["data"]["role"] == "member"


# ═══════════════════════════════════════════════════════════════════════════
# Role Change (uses admin_client)
# ═══════════════════════════════════════════════════════════════════════════


class TestRoleChange:
    """Test changing a member's role."""

    def test_change_member_role(self, admin_client):
        """PATCH /api/team/{user_id}/role -> role updated."""
        ms = admin_client.mock_supabase

        ms.set_table_responses("noctus_users", [
            # _require_team_manage -> _get_user_profile
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
            # target member lookup
            {"id": "target-user", "org_id": "test-org-123", "org_role": "member"},
            # update result
            {"id": "target-user", "org_id": "test-org-123", "org_role": "admin"},
        ])
        ms.set_table_responses("roles", [
            [{"id": "role-admin", "slug": "admin"}],
        ])

        resp = admin_client.patch("/api/team/target-user/role", json={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["data"]["org_role"] == "admin"


# ═══════════════════════════════════════════════════════════════════════════
# Remove Member (uses admin_client)
# ═══════════════════════════════════════════════════════════════════════════


class TestRemoveMember:
    """Test removing a member from the organization."""

    def test_remove_member(self, admin_client):
        """DELETE /api/team/{user_id} -> member removed."""
        ms = admin_client.mock_supabase

        ms.set_table_responses("noctus_users", [
            # _require_team_manage -> _get_user_profile
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
            # target member lookup
            {"id": "other-user", "org_id": "test-org-123", "org_role": "member"},
            # delete execute
            {"id": "other-user"},
        ])
        ms.set_table_data("audit_logs", [])
        ms.set_table_data("webhook_endpoints", [])

        resp = admin_client.delete("/api/team/other-user")
        assert resp.status_code == 200
        assert "removido" in resp.json()["message"].lower()

    def test_cannot_remove_owner(self, admin_client):
        """DELETE /api/team/{user_id} -> 403 if target is owner."""
        ms = admin_client.mock_supabase

        ms.set_table_responses("noctus_users", [
            # _require_team_manage
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
            # target member lookup -> owner
            {"id": "owner-user", "org_id": "test-org-123", "org_role": "owner"},
        ])

        resp = admin_client.delete("/api/team/owner-user")
        assert resp.status_code == 403

    def test_cannot_remove_self(self, admin_client):
        """DELETE /api/team/{self_id} -> 400."""
        ms = admin_client.mock_supabase

        ms.set_table_responses("noctus_users", [
            # _require_team_manage
            {"id": "admin-user-456", "org_id": "test-org-123", "org_role": "admin", "role": "admin"},
        ])

        # admin_client's user ID is "admin-user-456"
        resp = admin_client.delete("/api/team/admin-user-456")
        assert resp.status_code == 400
        body = resp.json()
        # Shared exception handler wraps errors in {"error": {"message": ...}}
        msg = body.get("detail", "") or body.get("error", {}).get("message", "")
        assert "si mesmo" in msg.lower()
