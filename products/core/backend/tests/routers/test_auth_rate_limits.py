"""
Rate-limit smoke tests for core auth surface — added by
`auth-rate-limit-rollout-2026-05-11`.

Strategy: each test fires (limit + 1) requests at a decorated endpoint
and asserts the LAST response is 429. We assert on `.status_code` only
(per the status-code-assertion rule); body shape coverage lives in the
existing per-endpoint test files.

The `_reset_rate_limiter` autouse fixture in `conftest.py` clears the
in-memory slowapi counters before/after every test, so these tests can
co-exist with the existing happy-path tests that hit the same routes.

Endpoints covered (matches §6 of the RATELIMIT-AUDIT project):
  - POST /api/sso/token             @ 20/min
  - POST /api/sso/validate          @ 20/min
  - GET  /api/sso/launch/{slug}     @ 20/min
  - POST /api/sso/session           @ 20/min
  - POST /api/auth/oauth/callback   @ 10/min
  - GET  /api/onboarding/status     @ 30/min
  - PATCH /api/onboarding/complete  @ 30/min
  - POST /api/admin/test-accounts   @ 5/min
  - GET  /api/admin/test-accounts   @ 5/min
  - DELETE /api/admin/test-accounts/{id} @ 5/min
  - POST /api/team/invite           @ 30/min
  - POST /api/team/accept-invite    @ 30/min
"""


# ---------------------------------------------------------------------------
# SSO router — 20/minute
# ---------------------------------------------------------------------------

class TestSSORateLimits:
    def test_sso_token_rate_limited(self, client):
        body = {"product_slug": "core"}
        # 21st call must hit the 20/min cap
        responses = [client.post("/api/sso/token", json=body) for _ in range(21)]
        assert responses[-1].status_code == 429

    def test_sso_validate_rate_limited(self, client):
        body = {"token": "fake-token"}
        responses = [client.post("/api/sso/validate", json=body) for _ in range(21)]
        assert responses[-1].status_code == 429

    def test_sso_launch_rate_limited(self, client):
        responses = [client.get("/api/sso/launch/core") for _ in range(21)]
        assert responses[-1].status_code == 429

    def test_sso_session_rate_limited(self, client):
        body = {"token": "fake-token"}
        responses = [client.post("/api/sso/session", json=body) for _ in range(21)]
        assert responses[-1].status_code == 429


# ---------------------------------------------------------------------------
# OAuth router — 10/minute on callback
# ---------------------------------------------------------------------------

class TestOAuthCallbackRateLimit:
    def test_oauth_callback_rate_limited(self, client):
        body = {"provider": "google"}
        responses = [client.post("/api/auth/oauth/callback", json=body) for _ in range(11)]
        assert responses[-1].status_code == 429


# ---------------------------------------------------------------------------
# Onboarding router — 30/minute on both endpoints
# ---------------------------------------------------------------------------

class TestOnboardingRateLimits:
    def test_onboarding_status_rate_limited(self, client):
        responses = [client.get("/api/onboarding/status") for _ in range(31)]
        assert responses[-1].status_code == 429

    def test_onboarding_complete_rate_limited(self, client):
        body = {"step": "company_details"}
        responses = [client.patch("/api/onboarding/complete", json=body) for _ in range(31)]
        assert responses[-1].status_code == 429


# ---------------------------------------------------------------------------
# Test-accounts router — 5/minute (sensitive)
# ---------------------------------------------------------------------------

class TestTestAccountsRateLimits:
    def test_create_test_account_rate_limited(self, admin_client):
        body = {
            "nome": "Test",
            "email": "t@example.com",
            "password": "secret-pw",
            "empresa": "TestCorp",
        }
        responses = [
            admin_client.post("/api/admin/test-accounts", json=body)
            for _ in range(6)
        ]
        assert responses[-1].status_code == 429

    def test_list_test_accounts_rate_limited(self, admin_client):
        responses = [admin_client.get("/api/admin/test-accounts") for _ in range(6)]
        assert responses[-1].status_code == 429

    def test_delete_test_account_rate_limited(self, admin_client):
        responses = [
            admin_client.delete("/api/admin/test-accounts/00000000-0000-0000-0000-000000000000")
            for _ in range(6)
        ]
        assert responses[-1].status_code == 429


# ---------------------------------------------------------------------------
# Team router — 30/minute on invite + accept-invite
# ---------------------------------------------------------------------------

class TestTeamRateLimits:
    def test_team_invite_rate_limited(self, client):
        body = {"email": "newmember@example.com", "role": "member"}
        responses = [client.post("/api/team/invite", json=body) for _ in range(31)]
        assert responses[-1].status_code == 429

    def test_team_accept_invite_rate_limited(self, client):
        body = {"token": "fake-token", "nome": "New Member"}
        responses = [
            client.post("/api/team/accept-invite", json=body)
            for _ in range(31)
        ]
        assert responses[-1].status_code == 429
