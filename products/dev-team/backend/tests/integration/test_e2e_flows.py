"""
E2E tests for the dev-team product — exercise the seed framework's standard
routers + the dev-team API surface as complete user journeys.

The dev-team product wraps the agno multi-agent engine (`dev_team/`) with
auth + multi-tenant + RLS. These flows verify the seed's standard routers
(health, team, notificacoes) are wired in this product, plus the dev-team
API surface (run/agents/metrics/configs) responds correctly.
"""


# ==========================================================================
# 1. Framework standard endpoints exist and respond
# ==========================================================================

class TestFrameworkEndpoints:
    """All seed-provided standard endpoints must exist + respond."""

    def test_health_returns_product_info(self, client):
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        # The seed populates `product` from create_product_app(name=...);
        # accept either form to keep the test framework-agnostic.
        assert data["product"] in ("dev-team", "Dev Team")
        assert "version" in data

    def test_team_list_requires_auth(self, client):
        assert client.raw().get("/api/team").status_code == 401

    def test_team_invite_requires_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "t@t.com"})
        assert resp.status_code == 401

    def test_notificacoes_list_requires_auth(self, client):
        assert client.raw().get("/api/notificacoes").status_code == 401

    def test_notificacoes_contagem_requires_auth(self, client):
        assert client.raw().get("/api/notificacoes/contagem").status_code == 401


# ==========================================================================
# 2. dev-team API surface — auth-gated
# ==========================================================================

class TestDevTeamAPISurfaceAuthBoundary:
    """The four dev-team router groups are behind auth. dev-team mounts its
    own routers at /api/run, /api/metrics, /api/agents, /api/configs — NOT
    under /api/team, which belongs to the seed Team-Management organ. Each
    endpoint hit without a token must return a strict 401: a (401, 404)
    disjunction is a false-green escape hatch — it passes even when the
    route is absent, so it can't tell "auth works" from "route missing"."""

    def test_run_endpoint_requires_auth(self, client):
        # POST /api/run dispatches the multi-agent team. `task` is a valid
        # RunRequest field so the body parses and the auth dep fires → 401.
        # (An unknown field would 422 on the StrictHttpModel before auth.)
        resp = client.raw().post("/api/run", json={"task": "x"})
        assert resp.status_code == 401

    def test_metrics_endpoint_requires_auth(self, client):
        assert client.raw().get("/api/metrics").status_code == 401

    def test_agents_endpoint_requires_auth(self, client):
        assert client.raw().get("/api/agents").status_code == 401

    def test_configs_endpoint_requires_auth(self, client):
        assert client.raw().get("/api/configs").status_code == 401


# ==========================================================================
# 3. Notification flow — basic round-trip via the seed router
# ==========================================================================

class TestNotificationFlow:
    """Notifications are provided by the seed's standard router. Verifies
    the router is correctly opted into via standard_routers=[...]."""

    def test_list_notifications(self, client):
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "user_id": "test-user-123", "type": "system",
             "title": "Welcome", "message": "Hello", "read": False,
             "metadata": {}, "created_at": "2026-01-01T00:00:00Z"},
        ])
        resp = client.get("/api/notificacoes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1

    def test_count_unread(self, client):
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1"}, {"id": "n2"},
        ])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["nao_lidas"] == 2


# ==========================================================================
# 4. Full auth boundary sweep — every protected endpoint rejects without token
# ==========================================================================

class TestAuthBoundary:
    def test_team_list_401(self, client):
        assert client.raw().get("/api/team").status_code == 401

    def test_team_invitations_401(self, client):
        assert client.raw().get("/api/team/invitations").status_code == 401

    def test_notificacoes_list_401(self, client):
        assert client.raw().get("/api/notificacoes").status_code == 401

    def test_notificacoes_mark_all_401(self, client):
        assert client.raw().post("/api/notificacoes/ler-todas").status_code == 401
