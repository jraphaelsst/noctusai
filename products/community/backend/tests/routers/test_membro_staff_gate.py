"""Foundation gate tests — contract §Roles / `app/dependencies.py`.

`get_current_user_org` must STRICTLY 403 a `membro` on every back-office
route (never `in (401, 403, ...)` — the false-green the platform's
auth-boundary rule exists to catch), while a staff role still reaches it.
`get_membro_context` is the mirror gate for the portal — covered by
`tests/routers/test_portal_router.py::TestPortalAuthBoundary`.
"""
from tests.conftest import seed_community_role


class TestBackOfficeGateDeniesMembro:
    def test_membro_read_route_is_403(self, client):
        seed_community_role(client, org_role="membro")
        resp = client.get("/api/membros")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Área restrita à equipe."

    def test_membro_write_route_is_403_before_require_admin(self, client):
        """A `membro`'s JWT never even reaches `require_admin` — the
        base auth gate refuses it first."""
        seed_community_role(client, org_role="membro")
        resp = client.post("/api/membros", json={
            "nome": "X", "email": "x@x.com", "origem": "checkout",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Área restrita à equipe."


class TestBackOfficeGateIsAnAllowList:
    """Staff is an ALLOW-list read from the trusted profile row. The org is
    shared with other products' users (e.g. 17 `corretor` rows live), who
    must never read Mônica's members (security review 2026-09-28, M7/H6)."""

    def test_other_products_role_is_403(self, client):
        seed_community_role(client, org_role="corretor")
        resp = client.get("/api/membros")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Área restrita à equipe."

    def test_null_org_role_is_403(self, client):
        seed_community_role(client, org_role=None)
        assert client.get("/api/membros").status_code == 403

    def test_no_profile_row_is_403_even_with_metadata_org(self, client):
        """No `noctus_users` row: the org would come from user-writable
        metadata, so the caller must be refused, not treated as staff."""
        client.mock_supabase.set_table_data("noctus_users", [])
        assert client.get("/api/membros").status_code == 403

    def test_spoofed_metadata_role_is_ignored(self, client):
        """`user_metadata` is writable by the user; only the profile row counts."""
        seed_community_role(client, org_role="corretor")
        user = client.mock_supabase.auth.get_user.return_value.user
        user.user_metadata = {**(user.user_metadata or {}), "role": "admin", "org_role": "admin"}
        assert client.get("/api/membros").status_code == 403

    def test_platform_admin_is_staff(self, client):
        seed_community_role(client, org_role="corretor", platform_role="admin")
        assert client.get("/api/membros").status_code == 200


class TestBackOfficeGateAllowsStaff:
    def test_admin_read_route_is_200(self, client):
        seed_community_role(client, org_role="admin")
        assert client.get("/api/membros").status_code == 200

    def test_moderador_read_route_is_200(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/membros").status_code == 200
