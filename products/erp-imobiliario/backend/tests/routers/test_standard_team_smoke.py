"""Mount-smoke tests for the seed `team` standard router on ERP.

Per PROJECT §6 Phase 7 / PF lessons §d.4: 5-test pattern — (a) route
exists, (b) auth gate, (c) happy-path 200, (d) wrong-org isolation
(the seed router scopes by `org_id` per `routers.py:114-117`), (e) shape.

The existing `test_team_router.py` covers business behavior (invite,
remove, role guards); this smoke file pins the MOUNT contract — that
the seed-mounted router exists at the documented path on THIS product
and isolates by org.

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`).
"""


class TestTeamStandardRouterMountSmoke:
    """`GET /api/team` — seed `team` router."""

    def test_route_exists(self, client):
        """(a) /api/team is mounted — not 404."""
        client._mock_supabase.set_table_data("noctus_users", [])
        resp = client.get("/api/team")
        assert resp.status_code != 404

    def test_requires_auth(self, client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_happy_path_returns_200_with_data(self, client):
        """(c) Happy path: authenticated GET returns 200 + member list."""
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "u-1", "name": "Alice", "email": "alice@test.com",
             "org_id": "test-org-123"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1

    def test_isolates_other_orgs_members(self, client):
        """(d) Wrong-org isolation: only the caller's org members surface.
        Seed router filters `.eq("org_id", org_id)` (routers.py:116).
        Default `mock_user.org_id` is `test-org-123`; seed a row for
        another org and assert it's filtered out by the mock."""
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "ours", "name": "Alice", "email": "alice@test.com",
             "org_id": "test-org-123"},
            {"id": "theirs", "name": "Bob", "email": "bob@other.com",
             "org_id": "other-org-456"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        ids = {m["id"] for m in resp.json()["data"]}
        assert ids == {"ours"}
        assert "theirs" not in ids

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `data` (a list) — the contract
        `_create_team_router` builds (seed routers.py:117)."""
        client._mock_supabase.set_table_data("noctus_users", [])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
