"""Team grant rules (org picker slice): ``owner`` is never grantable (invite or role
change); granting ``admin`` needs an inviter who is owner/admin or the platform
superadmin. Strict status codes. ``check_permission`` is allowed by the ``admin_client``
fixture, so these exercise the grant rule alone (a manager HOLDING team:manage)."""
import pytest

CALLER = "admin-user-456"


def _caller(mock_sb, org_role, role="user"):
    return {"id": CALLER, "org_id": "org-1", "org_role": org_role, "role": role, "nome": "C"}


def _invite_setup(mock_sb, org_role, role="user", target_slug="member"):
    mock_sb.set_table_responses("noctus_users", [
        _caller(mock_sb, org_role, role),
        [],
        {"id": CALLER, "nome": "C"},
    ])
    mock_sb.set_table_responses("invitations", [
        [],
        [{"id": "inv-1", "email": "n@example.com", "role": target_slug, "status": "pending", "token": "t"}],
    ])
    mock_sb.set_table_data("roles", [{"id": "r1", "slug": target_slug}])
    mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "Org"})


class TestInviteGrantRules:
    @pytest.mark.parametrize("org_role,role", [
        ("owner", "user"), ("admin", "user"), ("manager", "user"), ("member", "user"), ("owner", "admin"),
    ])
    def test_owner_is_never_grantable_by_invite(self, admin_client, org_role, role):
        _invite_setup(admin_client.mock_supabase, org_role, role, "owner")
        resp = admin_client.post("/api/team/invite", json={"email": "n@example.com", "role": "owner"})
        assert resp.status_code == 403

    def test_manager_cannot_invite_an_admin(self, admin_client):
        _invite_setup(admin_client.mock_supabase, "manager", "user", "admin")
        resp = admin_client.post("/api/team/invite", json={"email": "n@example.com", "role": "admin"})
        assert resp.status_code == 403

    @pytest.mark.parametrize("org_role,role", [("owner", "user"), ("admin", "user"), ("manager", "admin")])
    def test_owner_admin_or_superadmin_can_invite_an_admin(self, admin_client, org_role, role):
        _invite_setup(admin_client.mock_supabase, org_role, role, "admin")
        resp = admin_client.post("/api/team/invite", json={"email": "n@example.com", "role": "admin"})
        assert resp.status_code == 200

    def test_manager_can_still_invite_a_member(self, admin_client):
        _invite_setup(admin_client.mock_supabase, "manager", "user", "member")
        resp = admin_client.post("/api/team/invite", json={"email": "n@example.com", "role": "member"})
        assert resp.status_code == 200


class TestRoleChangeGrantRules:
    def test_owner_is_never_grantable_by_role_change(self, admin_client):
        admin_client.mock_supabase.set_table_data("noctus_users", _caller(None, "owner", "admin"))
        admin_client.mock_supabase.set_table_data("roles", [{"id": "r", "slug": "owner"}])
        resp = admin_client.patch("/api/team/other-user/role", json={"role": "owner"})
        assert resp.status_code == 403

    def test_manager_cannot_promote_to_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            _caller(mock_sb, "manager"),
            {"id": "other-user", "org_id": "org-1", "org_role": "member"},
            [{"id": "other-user", "org_id": "org-1", "org_role": "admin"}],
        ])
        mock_sb.set_table_data("roles", [{"id": "r1", "slug": "admin"}])
        resp = admin_client.patch("/api/team/other-user/role", json={"role": "admin"})
        assert resp.status_code == 403

    def test_manager_can_still_set_a_non_admin_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            _caller(mock_sb, "manager"),
            {"id": "other-user", "org_id": "org-1", "org_role": "member"},
            [{"id": "other-user", "org_id": "org-1", "org_role": "viewer"}],
        ])
        mock_sb.set_table_data("roles", [{"id": "r1", "slug": "viewer"}])
        resp = admin_client.patch("/api/team/other-user/role", json={"role": "viewer"})
        assert resp.status_code == 200


class TestUsersRouterRoleChangesStaySuperadminOnly:
    """noctus_users.role / org_role / org_id are writable ONLY through the superadmin-gated
    users router -- an org owner (not platform admin) is refused 403."""

    def test_org_owner_cannot_patch_platform_role(self, client):
        for body in ({"role": "admin"}, {"org_role": "owner"}):
            resp = client.patch("/api/admin/users/some-user", json=body)
            assert resp.status_code == 403
