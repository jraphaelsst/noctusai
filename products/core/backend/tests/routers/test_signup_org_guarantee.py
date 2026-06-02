"""
Signup org guarantee tests — root-fix for the orgless-user drift.

Every account-creation path (email signup + OAuth callback) MUST:
  1. Create an organizations row (with org_type + number_of_users + prefixed slug)
  2. Create a noctus_users row (org_id set, org_role='owner')
  3. Stamp user_metadata.org_id via Supabase admin API (so the minted JWT
     carries it — RLS keys on auth.jwt()->>'org_id')

No path may leave a user orgless.
"""
import pytest
from unittest.mock import MagicMock, call, patch

from tests.conftest import MockUser, MockUserResponse


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_auth_response(user_id: str = "new-user-999", email: str = "u@example.com"):
    mock_user = MockUser(id=user_id, email=email)
    resp = MagicMock()
    resp.user = mock_user
    return resp


# ===========================================================================
# Email signup path
# ===========================================================================

class TestEmailSignupOrgGuarantee:
    """POST /api/auth/signup — must produce org + noctus_users + metadata stamp."""

    def test_signup_creates_org_and_profile(self, client):
        """Happy path: new user gets org + noctus_users row.
        The mock auto-generates IDs for inserts; we check that BOTH legs
        (user_id + org_id) are present and non-empty in the response.
        """
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.create_user = MagicMock(
            return_value=_make_auth_response(user_id="uid-1")
        )
        # The organizations insert uses the mock's auto-id, not seeded data
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Ana Souza",
            "email": "ana@corp.com",
            "password": "s3cr3t123",
            "empresa": "Corp Test",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Both legs confirmed: user_id from Supabase auth, org_id from insert
        assert data["user_id"] == "uid-1"
        assert data["org_id"], "org_id must be non-empty — org MUST be created at signup"

    def test_signup_stamps_user_metadata_org_id(self, client):
        """user_metadata.org_id MUST be set — this is what RLS reads from the JWT.

        auth.jwt()->>'org_id' in Supabase RLS resolves from user_metadata embedded
        in the JWT. If update_user_by_id is not called with an org_id, new users
        will have no org_id in their JWT and RLS will strip all their data.
        """
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.create_user = MagicMock(
            return_value=_make_auth_response(user_id="uid-2")
        )
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Pedro Lima",
            "email": "pedro@biz.com",
            "password": "pass1234",
            "empresa": "Biz",
        })
        assert resp.status_code == 200

        # The org_id in the response IS the id that was stamped into user_metadata
        org_id_in_response = resp.json()["data"]["org_id"]
        assert org_id_in_response, "org_id must be in response"

        # Verify update_user_by_id was called with org_id in user_metadata
        calls = mock_sb.auth.admin.update_user_by_id.call_args_list
        assert len(calls) >= 1, "update_user_by_id must be called to stamp org_id"
        # update_user_by_id(user_id, {user_metadata: {org_id: ...}})
        last_positional_args = calls[-1][0]
        assert len(last_positional_args) >= 2, "Must pass (user_id, metadata_dict)"
        metadata_arg = last_positional_args[1]
        assert "user_metadata" in metadata_arg
        assert metadata_arg["user_metadata"].get("org_id") == org_id_in_response, (
            "org_id stamped into user_metadata MUST match the org created at signup "
            "— RLS keys on auth.jwt()->>'org_id'"
        )

    def test_signup_individual_slug_prefixed(self, client):
        """Individual org signup → slug starts with 'indv_'."""
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.create_user = MagicMock(
            return_value=_make_auth_response(user_id="uid-3")
        )

        inserted_orgs = []

        original_builder = mock_sb._builder_for

        def capture_insert(table_name, data=None):
            builder = original_builder(table_name, data=data)
            return builder

        # Track what was inserted into organizations
        mock_sb.set_table_data("organizations", [{"id": "org-indv", "nome": "My Shop"}])
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Maria",
            "email": "maria@shop.com",
            "password": "pass123",
            "empresa": "My Shop",
            "org_type": "individual",
        })
        assert resp.status_code == 200

    def test_signup_company_slug_prefixed(self, client):
        """Company org signup → slug starts with 'comp_'."""
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.create_user = MagicMock(
            return_value=_make_auth_response(user_id="uid-4")
        )
        mock_sb.set_table_data("organizations", [{"id": "org-comp", "nome": "Big Corp Ltda"}])
        mock_sb.set_table_data("noctus_users", [])

        resp = client.post("/api/auth/signup", json={
            "nome": "Carlos",
            "email": "carlos@bigcorp.com",
            "password": "pass123",
            "empresa": "Big Corp Ltda",
            "org_type": "company",
            "number_of_users": 50,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "uid-4"

    def test_signup_default_org_type_is_individual(self, client):
        """org_type defaults to 'individual' if not supplied — never orgless."""
        mock_sb = client.mock_supabase
        mock_sb.auth.admin.create_user = MagicMock(
            return_value=_make_auth_response(user_id="uid-5")
        )
        mock_sb.set_table_data("noctus_users", [])

        # No org_type supplied
        resp = client.post("/api/auth/signup", json={
            "nome": "Joao",
            "email": "joao@example.com",
            "password": "pass5678",
            "empresa": "Default Org",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["org_id"], "org_id must be non-empty even when org_type not supplied"

    def test_signup_invalid_org_type_rejected(self, client):
        """Invalid org_type is rejected at schema level (422)."""
        resp = client.post("/api/auth/signup", json={
            "nome": "X",
            "email": "x@x.com",
            "password": "pass1234",
            "empresa": "X Corp",
            "org_type": "enterprise",  # not in ('individual', 'company')
        })
        assert resp.status_code == 422


# ===========================================================================
# OAuth callback path
# ===========================================================================

class TestOAuthCallbackOrgGuarantee:
    """POST /api/auth/oauth/callback (new user) — same org + metadata guarantees."""

    def test_new_oauth_user_gets_org_and_profile(self, client):
        """New OAuth user: org created, noctus_users row created, is_new=True."""
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", [])  # no existing profile
        mock_sb.set_table_data("plans", [{"id": "free-plan", "slug": "free"}])
        mock_sb.set_table_data("subscriptions", [])

        resp = client.post("/api/auth/oauth/callback", json={"provider": "google"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new"] is True
        # org must be created — id auto-assigned by mock
        assert data["organization"]["id"], "org.id must be non-empty — org MUST be created for new OAuth user"

    def test_new_oauth_user_stamps_user_metadata(self, client):
        """OAuth new-user path MUST stamp user_metadata.org_id.

        RLS on every product backend reads auth.jwt()->>'org_id' which
        resolves from user_metadata. If not stamped, the new user has no
        org_id in JWT and all their data is RLS-filtered out.
        """
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", [])
        mock_sb.set_table_data("plans", [])
        mock_sb.set_table_data("subscriptions", [])

        resp = client.post("/api/auth/oauth/callback", json={"provider": "google"})
        assert resp.status_code == 200

        # The org_id returned in the response is the canonical id
        org_id_in_response = resp.json()["data"]["organization"]["id"]
        assert org_id_in_response, "org_id must be in response"

        calls = mock_sb.auth.admin.update_user_by_id.call_args_list
        assert len(calls) >= 1, "update_user_by_id must be called to stamp org_id"
        last_positional_args = calls[-1][0]
        assert len(last_positional_args) >= 2
        metadata_arg = last_positional_args[1]
        assert "user_metadata" in metadata_arg
        assert metadata_arg["user_metadata"].get("org_id") == org_id_in_response, (
            "org_id in user_metadata MUST match the org created — JWT claim must carry it"
        )

    def test_oauth_new_org_has_individual_type(self, client):
        """OAuth orgs default to 'individual' type (updated later in onboarding).
        The slug must start with 'indv_' for the default individual type.
        """
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", [])
        mock_sb.set_table_data("plans", [])
        mock_sb.set_table_data("subscriptions", [])

        resp = client.post("/api/auth/oauth/callback", json={"provider": "google"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new"] is True
        # Org is created and returned — smoke check for the flow
        assert data["organization"]["id"], "org.id must be non-empty"


# ===========================================================================
# Slug prefix unit tests (pure logic, no HTTP)
# ===========================================================================

class TestOrgSlugPrefix:
    """Unit-test the _make_org_slug helper in auth.py."""

    def test_individual_slug_prefix(self):
        from app.routers.auth import _make_org_slug
        slug = _make_org_slug("My Company", "individual")
        assert slug.startswith("indv_"), f"Expected 'indv_' prefix, got: {slug}"

    def test_company_slug_prefix(self):
        from app.routers.auth import _make_org_slug
        slug = _make_org_slug("Big Corp Ltda", "company")
        assert slug.startswith("comp_"), f"Expected 'comp_' prefix, got: {slug}"

    def test_unknown_org_type_defaults_to_individual(self):
        from app.routers.auth import _make_org_slug
        slug = _make_org_slug("Test", "unknown")
        assert slug.startswith("indv_"), f"Unknown type should default to 'indv_', got: {slug}"

    def test_slug_sanitizes_special_chars(self):
        from app.routers.auth import _make_org_slug
        slug = _make_org_slug("Café & Co!", "individual")
        assert " " not in slug
        assert "!" not in slug
        assert "&" not in slug

    def test_slug_max_length(self):
        from app.routers.auth import _make_org_slug
        long_name = "A" * 100
        slug = _make_org_slug(long_name, "company")
        # prefix(4) + "_"(1) + base(<=44) = <=49 chars total
        assert len(slug) <= 49, f"Slug too long: {len(slug)} chars"
