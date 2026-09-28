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


class TestBackOfficeGateAllowsStaff:
    def test_admin_read_route_is_200(self, client):
        seed_community_role(client, org_role="admin")
        assert client.get("/api/membros").status_code == 200

    def test_moderador_read_route_is_200(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/membros").status_code == 200
