"""Mount-smoke tests for the seed `notificacoes` standard router on ERP.

Per PROJECT §6 Phase 7 / PF lessons §d.4: 5-test pattern — (a) route
exists, (b) auth gate, (c) happy-path 200, (d) wrong-user isolation
(the seed router scopes by `user_id` per `routers.py:70`), (e) shape.

The existing `test_notificacoes_router.py` covers business behavior
(pagination, count, mark-read); this smoke file pins the MOUNT
contract — that the seed-mounted router exists at the documented path
with the documented isolation semantics on THIS product.

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`).
"""


class TestNotificacoesStandardRouterMountSmoke:
    """`GET /api/notificacoes` — seed `notificacoes` router."""

    def test_route_exists(self, client):
        """(a) /api/notificacoes is mounted — not 404."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.get("/api/notificacoes")
        assert resp.status_code != 404

    def test_requires_auth(self, client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401

    def test_happy_path_returns_200_with_data(self, client):
        """(c) Happy path: authenticated GET returns 200 + envelope."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "type": "novo_lead", "title": "Lead",
             "message": "Hi", "is_read": False,
             "created_at": "2026-05-20T10:00:00",
             "metadata": {}, "user_id": "test-user-123",
             "org_id": "test-org-123"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1

    def test_isolates_other_users_notifications(self, client):
        """(d) Wrong-user isolation: only the caller's notifications surface.
        Seed router filters `.eq("user_id", str(user.id))` (routers.py:70).
        Default `mock_user` is `test-user-123`; seed a row for `other-user`
        and assert it's filtered out by the mock's `.eq()` honoring."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "mine", "type": "x", "title": "mine", "is_read": False,
             "created_at": "2026-05-20T10:00:00", "metadata": {},
             "user_id": "test-user-123", "org_id": "test-org-123"},
            {"id": "theirs", "type": "x", "title": "theirs", "is_read": False,
             "created_at": "2026-05-20T10:00:00", "metadata": {},
             "user_id": "other-user-456", "org_id": "other-org"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        ids = {n["id"] for n in resp.json()["data"]}
        assert ids == {"mine"}
        assert "theirs" not in ids

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `data`, `total`, `page`,
        `page_size` — the contract `_create_notificacoes_router` builds
        (seed routers.py:76)."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert {"data", "total", "page", "page_size"}.issubset(body.keys())
