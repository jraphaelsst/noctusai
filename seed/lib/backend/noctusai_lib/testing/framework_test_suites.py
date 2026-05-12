"""
Reusable test base classes for the seed framework's standard endpoints.

These suites lift the framework-test scaffolding that recurred verbatim across
N=4-7 products into a single source of truth. Each adopter collapses from
~30 LOC of identical assertions to a 3-line subclass overriding the
product-specific class attributes.

Usage::

    # products/<x>/backend/tests/routers/test_health.py
    from noctusai_lib.testing import HealthCheckSuite

    class TestHealthCheck(HealthCheckSuite):
        expected_product_name = "AdConnect"

The ``client`` fixture is resolved from the consumer product's
``conftest.py`` — every adopter ships the same ``AuthClient``-yielding
fixture, so the suites simply consume it by name.

Convention — every test asserts on response status code BEFORE asserting on
body. The ``check_test_status_assertion`` keeper detector enforces this rule
across the codebase; lifting these suites into a single file means the rule
gets enforced at one place instead of N copies.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Health endpoint — provided by seed framework
# ---------------------------------------------------------------------------

class HealthCheckSuite:
    """GET /api/health — public endpoint provided by the seed framework.

    Subclass and override ``expected_product_name`` (and optionally
    ``expected_version``) to plug your product's display name in.

    Lifted verbatim from the canonical seed/adconnect/media-scheduling/
    youtube-crawler shape (4 byte-identical copies pre-absorption).
    """

    #: Product display name — subclasses MUST override.
    expected_product_name: str = "Seed Product"
    #: Expected version string — defaults match the seed framework's
    #: scaffold default; rarely needs overriding.
    expected_version: str = "0.1.0"

    def test_health_returns_ok(self, client):
        """Health endpoint returns status ok with product info."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == self.expected_product_name
        assert data["version"] == self.expected_version


# ---------------------------------------------------------------------------
# Team router — provided by seed framework
# ---------------------------------------------------------------------------

#: Default member fixture used by team-router suites. Override via class attr
#: if your product needs a different shape.
_DEFAULT_SAMPLE_MEMBER = {
    "id": "m1",
    "nome": "Membro Seed",
    "email": "membro@test.com",
    "org_role": "member",
    "avatar_url": None,
    "created_at": "2026-01-01T00:00:00",
}

#: Default user-id used in delete/no-auth probes.
_DEFAULT_USER_ID = "test-user-123"


class TeamRouterListMembersSuite:
    """GET /api/team — framework's team-list endpoint.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption).
    """

    sample_member: dict = _DEFAULT_SAMPLE_MEMBER

    def test_list_members(self, client):
        """GET /api/team returns org members."""
        client._mock_supabase.set_table_data("noctus_users", [self.sample_member])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_members_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401


class TeamRouterInviteSuite:
    """POST /api/team/invite — framework's team-invite endpoint.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption).
    """

    invite_email: str = "test@test.com"
    invite_role: str = "member"

    def test_invite_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().post("/api/team/invite", json={
            "email": self.invite_email,
            "role": self.invite_role,
        })
        assert resp.status_code == 401


class TeamRouterRemoveMemberSuite:
    """DELETE /api/team/{user_id} — framework's team-remove endpoint.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption).
    """

    target_user_id: str = _DEFAULT_USER_ID

    def test_remove_no_auth(self, client):
        """401 when no authorization header."""
        resp = client.raw().delete(f"/api/team/{self.target_user_id}")
        assert resp.status_code == 401

    def test_remove_requires_admin(self, client):
        """403 when non-admin tries to remove a member."""
        resp = client.delete(f"/api/team/{self.target_user_id}")
        assert resp.status_code in (400, 403)


# ---------------------------------------------------------------------------
# E2E framework-flow suites
# ---------------------------------------------------------------------------

class FrameworkEndpointsSuite:
    """All framework-provided endpoints must exist and respond.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption). Subclasses override
    ``expected_product_name`` to match their /api/health response.
    """

    expected_product_name: str = "Seed Product"

    def test_health_returns_product_info(self, client):
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["product"] == self.expected_product_name
        assert "version" in data

    def test_team_list_requires_auth(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_team_invite_requires_auth(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "t@t.com"})
        assert resp.status_code == 401

    def test_team_validate_requires_token(self, client):
        resp = client.raw().get("/api/team/accept/validate")
        assert resp.status_code == 422  # missing query param

    def test_team_invitations_requires_auth(self, client):
        resp = client.raw().get("/api/team/invitations")
        assert resp.status_code == 401

    def test_team_delete_requires_auth(self, client):
        resp = client.raw().delete("/api/team/some-id")
        assert resp.status_code == 401

    def test_notificacoes_list_requires_auth(self, client):
        resp = client.raw().get("/api/notificacoes")
        assert resp.status_code == 401

    def test_notificacoes_contagem_requires_auth(self, client):
        resp = client.raw().get("/api/notificacoes/contagem")
        assert resp.status_code == 401

    def test_notificacoes_mark_read_requires_auth(self, client):
        resp = client.raw().patch("/api/notificacoes/some-id/ler")
        assert resp.status_code == 401

    def test_notificacoes_mark_all_requires_auth(self, client):
        resp = client.raw().post("/api/notificacoes/ler-todas")
        assert resp.status_code == 401


class TeamFlowSuite:
    """Authenticated team-management flow through the framework router.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption).
    """

    def test_list_members_returns_data(self, client):
        """Authenticated user can list org members.

        Seeded rows include ``org_id`` matching the conftest-bound
        ``MockUser(org_id="test-org-123")`` so the production
        ``.eq("org_id", org_id)`` filter in
        ``noctusai_seed.routers._create_team_router`` returns both rows
        instead of empty. Without ``org_id`` the filter drops every row
        and ``len(data) == 2`` fails.
        """
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Alice", "email": "alice@test.com",
             "org_id": "test-org-123", "org_role": "owner",
             "avatar_url": None, "created_at": "2026-01-01T00:00:00Z"},
            {"id": "u2", "nome": "Bob", "email": "bob@test.com",
             "org_id": "test-org-123", "org_role": "member",
             "avatar_url": None, "created_at": "2026-01-02T00:00:00Z"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_cannot_remove_self(self, client):
        """Framework prevents self-removal."""
        resp = client.delete("/api/team/test-user-123")
        # Returns 400 (self-removal) or 403 (not admin) — both are correct rejections
        assert resp.status_code in (400, 403)


class NotificationFlowSuite:
    """Notification proxying through the framework's standard router.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption).
    """

    def test_list_notifications(self, client):
        """Authenticated user can list notifications."""
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
        """Count unread notifications."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1"}, {"id": "n2"},
        ])
        resp = client.get("/api/notificacoes/contagem")
        assert resp.status_code == 200
        assert resp.json()["nao_lidas"] == 2

    def test_mark_one_as_read(self, client):
        """Mark a single notification as read."""
        client._mock_supabase.set_table_data("notifications", [
            {"id": "n1", "read": True},
        ])
        resp = client.patch("/api/notificacoes/n1/ler")
        assert resp.status_code == 200

    def test_mark_all_as_read(self, client):
        """Mark all notifications as read."""
        client._mock_supabase.set_table_data("notifications", [])
        resp = client.post("/api/notificacoes/ler-todas")
        assert resp.status_code == 200


class AuthBoundarySuite:
    """Every protected framework endpoint must return 401 without auth.

    Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler
    (4 byte-identical copies pre-absorption). Covers ONLY the framework's
    standard endpoints — products with extra protected routes (mailing,
    daily-life) keep their per-product TestAuthBoundary in addition to (or
    instead of) consuming this suite.
    """

    def test_team_list_401(self, client):
        assert client.raw().get("/api/team").status_code == 401

    def test_team_invite_401(self, client):
        assert client.raw().post("/api/team/invite", json={"email": "t@t.com"}).status_code == 401

    def test_team_invitations_401(self, client):
        assert client.raw().get("/api/team/invitations").status_code == 401

    def test_team_cancel_401(self, client):
        assert client.raw().delete("/api/team/invitations/x").status_code == 401

    def test_team_remove_401(self, client):
        assert client.raw().delete("/api/team/x").status_code == 401

    def test_notificacoes_list_401(self, client):
        assert client.raw().get("/api/notificacoes").status_code == 401

    def test_notificacoes_contagem_401(self, client):
        assert client.raw().get("/api/notificacoes/contagem").status_code == 401

    def test_notificacoes_mark_401(self, client):
        assert client.raw().patch("/api/notificacoes/x/ler").status_code == 401

    def test_notificacoes_mark_all_401(self, client):
        assert client.raw().post("/api/notificacoes/ler-todas").status_code == 401


__all__ = [
    "HealthCheckSuite",
    "TeamRouterListMembersSuite",
    "TeamRouterInviteSuite",
    "TeamRouterRemoveMemberSuite",
    "FrameworkEndpointsSuite",
    "TeamFlowSuite",
    "NotificationFlowSuite",
    "AuthBoundarySuite",
]
