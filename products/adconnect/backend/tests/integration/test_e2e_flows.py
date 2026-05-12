"""
E2E tests for the AdConnect — validates the seed framework's standard
routers work as complete user journeys.

These tests prove the framework itself works. If these fail, every product
that inherits from the framework is affected.

Inherits from `noctusai_lib.testing` framework-test suites (lifted from N=4
byte-identical copies; see `seed/lib/backend/noctusai_lib/testing/
framework_test_suites.py`).
"""
from noctusai_lib.testing import (
    FrameworkEndpointsSuite,
    TeamFlowSuite,
    NotificationFlowSuite,
    AuthBoundarySuite,
)

from tests.conftest import ORG_ID_BRAND


class TestFrameworkEndpoints(FrameworkEndpointsSuite):
    expected_product_name = "AdConnect"


class TestTeamFlow(TeamFlowSuite):
    """Adconnect's `client` fixture binds `MockUser(org_id=ORG_ID_BRAND)`
    rather than the seed-default ``test-org-123``. The TeamFlowSuite's
    seeded `noctus_users` rows carry the literal ``test-org-123`` so the
    production `.eq("org_id", org_id)` filter in
    ``noctusai_seed.routers._create_team_router`` drops every row.

    Override `test_list_members_returns_data` here with rows carrying
    ``org_id=ORG_ID_BRAND`` so they pass the predicate filter.
    """

    def test_list_members_returns_data(self, client):
        client._mock_supabase.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Alice", "email": "alice@test.com",
             "org_id": ORG_ID_BRAND, "org_role": "owner",
             "avatar_url": None, "created_at": "2026-01-01T00:00:00Z"},
            {"id": "u2", "nome": "Bob", "email": "bob@test.com",
             "org_id": ORG_ID_BRAND, "org_role": "member",
             "avatar_url": None, "created_at": "2026-01-02T00:00:00Z"},
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2


class TestNotificationFlow(NotificationFlowSuite):
    pass


class TestAuthBoundary(AuthBoundarySuite):
    pass
